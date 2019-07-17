# Copyright 2018-present Kensho Technologies, LLC.
"""Transform a SqlNode tree into an executable SQLAlchemy query."""
from collections import namedtuple
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Column, bindparam, select
import sqlalchemy.dialects.mssql as mssql
from sqlalchemy.sql import expression as sql_expressions
from sqlalchemy.sql.elements import BindParameter, and_

from . import sql_context_helpers
from ..compiler import expressions
from .helpers import GraphQLCompilationError
import sqlalchemy
import six
import unittest
from . import compiler_frontend, blocks, helpers, expressions


def split_blocks(ir_blocks):
    if not isinstance(ir_blocks[0], blocks.QueryRoot):
        raise AssertionError(u'TODO')

    start_classname = helpers.get_only_element_from_collection(ir_blocks[0].start_class)
    local_operations = []
    found_global_operations_block = False
    global_operations = []
    for block in ir_blocks[1:]:
        if isinstance(block, blocks.QueryRoot):
            raise AssertionError(u'TODO')
        elif isinstance(block, blocks.GlobalOperationsStart):
            if found_global_operations_block:
                raise AssertionError(u'TODO')
            found_global_operations_block = True
        if found_global_operations_block:
            global_operations.append(block)
        else:
            local_operations.append(block)
    return start_classname, local_operations, global_operations


def _get_local_fields_used(expression):
    # HACK it doesn't handle all cases
    if isinstance(expression, expressions.BinaryComposition):
        return _get_local_fields_used(expression.left) + _get_local_fields_used(expression.right)
    elif isinstance(expression, expressions.LocalField):
        return [expression]
    else:
        return []


def emit_sql(ir_blocks, query_metadata_table, compiler_metadata):
    """Emit SQLAlchemy from IR.

    Args:
        - ir: IR
        - tables: dict from graphql vertex names to sqlalchemy tables. The tables can come from different
          metadatas, and live in different tables, it doesn't really matter. If they do come from different
          databases, their table.schema should contain '<database_name>.<schema_name>'.
        - sql_edges: dict mapping graphql classes to:
                        dict mapping edge fields at that class to a dict with the following info:
                           to_table: GrapqQL vertex where the edge ends up
                           from_column: column name in this table
                           to_column: column name in tables[to_table]. The join is done on the from_column
                                      and to_column being equal. If you really need other kinds of joins,
                                      feel free to extend the interface.
    """
    tables = compiler_metadata.table_name_to_table
    sql_edges = compiler_metadata.joins

    current_classname, local_operations, global_operations = split_blocks(ir_blocks)
    current_location = query_metadata_table.root_location
    if current_classname not in tables:
        raise AssertionError(u'Class {} exists in the schema, but not in the SqlMetadata tables'
                             .format(current_classname))
    current_alias = tables[current_classname].alias()
    alias_at_location = {}  # Updated only at MarkLocation blocks. Maps query path to alias

    from_clause = current_alias
    outputs = []
    filters = []

    for block in local_operations:
        if isinstance(block, (blocks.EndOptional)):
            pass  # Nothing to do
        elif isinstance(block, blocks.MarkLocation):
            alias_at_location[current_location.query_path] = current_alias
        elif isinstance(block, blocks.Backtrack):
            current_location = block.location
            current_alias = alias_at_location[current_location.query_path]
            current_classname = query_metadata_table.get_location_info(current_location).type.name
        elif isinstance(block, blocks.Traverse):
            previous_alias = current_alias
            edge_field = u'{}_{}'.format(block.direction, block.edge_name)
            current_location = current_location.navigate_to_subpath(edge_field)
            if edge_field not in sql_edges.get(current_classname, {}):
                raise AssertionError(u'Edge {} from {} exists in the schema, but not in the '
                                     u'SqlMetadata edges'.format(edge_field, current_classname))
            edge = sql_edges[current_classname][edge_field]
            current_alias = tables[edge['to_table']].alias()
            current_classname = query_metadata_table.get_location_info(current_location).type.name

            from_clause = from_clause.join(
                current_alias,
                onclause=(previous_alias.c[edge['from_column']] == current_alias.c[edge['to_column']]),
                isouter=block.optional)
        elif isinstance(block, blocks.Filter):
            sql_predicate = block.predicate.to_sql(alias_at_location, current_alias)

            # HACK filters in optionals are hard. This is wrong.
            if query_metadata_table.get_location_info(current_location).optional_scopes_depth > 0:
                sql_predicate = sqlalchemy.or_(sql_predicate, *[
                    expressions.BinaryComposition(u'=', local_field, expressions.Literal(None)).to_sql(
                        alias_at_location, current_alias)
                    for local_field in _get_local_fields_used(block.predicate)
                ])

            filters.append(sql_predicate)
        else:
            raise NotImplementedError(u'{}'.format(block))

    current_location = None
    for block in global_operations:
        if isinstance(block, blocks.ConstructResult):
            for output_name, field in six.iteritems(block.fields):

                # HACK for outputs in optionals. Wrong on so many levels
                if isinstance(field, expressions.TernaryConditional):
                    field = field.if_true

                outputs.append(field.to_sql(alias_at_location, current_alias).label(output_name))

    return sqlalchemy.select(outputs).select_from(from_clause).where(sqlalchemy.and_(*filters))


def print_mssql_query(statement):
    """
    Print a query, with values filled in for debugging purposes *only* for security, you should
    always separate queries from their values. Please also note that this function is quite slow.
    Inspiration from:
    https://stackoverflow.com/questions/5631078/sqlalchemy-print-the-actual-query/5698357
    """
    compiler = statement._compiler(mssql.dialect())
    class LiteralCompiler(compiler.__class__):
        def visit_bindparam(
                self, bindparam, within_columns_clause=False,
                literal_binds=False, **kwargs
        ):
            return super(LiteralCompiler, self).render_literal_bindparam(
                    bindparam, within_columns_clause=within_columns_clause,
                    literal_binds=literal_binds, **kwargs
            )

        def render_literal_bindparam(self, bindparam, **kw):
            value = bindparam.effective_value
            if isinstance(value, list):
                for sub_value in value:
                    if isinstance(sub_value, list):
                        raise GraphQLCompilationError('Param {} is a nested list. No nested lists '
                                                      'allowed'.format(bindparam.key))
                    if not isinstance(sub_value, bindparam.type.python_object):
                        raise GraphQLCompilationError('Param {} is a list with a value {} that is '
                                                      'not of the expected type {}.'
                                                      .format(bindparam.key, sub_value,
                                                              str(bindparam.type.python_object)))
            else:
                # This SQLAlchemy type does not have a python_type implementation.
                if isinstance(bindparam.type, mssql.UNIQUEIDENTIFIER):
                    if not isinstance(value, str):
                        raise GraphQLCompilationError('Param {} is not of the expected type {}.'
                                                      .format(value, str))
                # This SQLAlchemy type does not have a python_type implementation.
                elif isinstance(bindparam.type, mssql.BIT):
                    if not isinstance(value, bool):
                        raise GraphQLCompilationError('Param {} is not of the expected type {}.'
                                                      .format(value, bool))
                elif not isinstance(value, bindparam.type.python_object):
                    raise GraphQLCompilationError('Param {} is not of the expected type {}.'
                          .format(value, str(bindparam.type.python_object)))
            return self.render_literal_value(value, bindparam.type)

        def render_literal_value(self, value, type_):
            if isinstance(value, (list, tuple)):
                return "(%s)" % (",".join([self.render_literal_value(x, type_) for x in value]))
            else:
                if value is None:
                    return 'NULL'
                elif isinstance(value, bool):
                    return '1' if value else '0'
                elif isinstance(value, (int, float, Decimal)):
                    return str(value)
                elif isinstance(value, str):
                    return "'%s'" % value.replace("'", "''")
                elif isinstance(value, datetime):
                    return "{ts '%04d-%02d-%02d %02d:%02d:%02d.%03d'}" % (
                        value.year, value.month, value.day,
                        value.hour, value.minute, value.second,
                        value.microsecond / 1000)
                elif isinstance(value, date):
                    return "{d '%04d-%02d-%02d'} " % (
                        value.year, value.month, value.day)
            return super(LiteralCompiler, self).render_literal_value(value, type_)

    compiler = LiteralCompiler(mssql.dialect(), statement)
    return str(compiler.process(statement))
