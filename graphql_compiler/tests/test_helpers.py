# Copyright 2017-present Kensho Technologies, LLC.
"""Common test data and helper functions."""
from pprint import pformat
import re

from graphql import parse
from graphql.utils.build_ast_schema import build_ast_schema
import six

from .. import get_graphql_schema_from_orientdb_schema_data
from ..debugging_utils import pretty_print_gremlin, pretty_print_match
from ..schema_generation.orientdb.schema_graph_builder import get_orientdb_schema_graph
from ..schema_generation.orientdb.utils import (
    ORIENTDB_INDEX_RECORDS_QUERY, ORIENTDB_SCHEMA_RECORDS_QUERY
)


# The strings which we will be comparing have newlines and spaces we'd like to get rid of,
# so we can compare expected and produced emitted code irrespective of whitespace.
WHITESPACE_PATTERN = re.compile(u'[\t\n ]*', flags=re.UNICODE)

# flag to indicate a test component should be skipped
SKIP_TEST = 'SKIP'

# Text representation of a GraphQL schema generated from OrientDB.
# This schema isn't meant to be a paragon of good schema design.
# Instead, it aims to capture as many real-world edge cases as possible,
# without requiring a massive number of types and interfaces.
SCHEMA_TEXT = '''
    schema {
        query: RootSchemaQuery
    }

    directive @filter(op_name: String!, value: [String!]!) on FIELD | INLINE_FRAGMENT

    directive @tag(tag_name: String!) on FIELD

    directive @output(out_name: String!) on FIELD

    directive @output_source on FIELD

    directive @optional on FIELD

    directive @recurse(depth: Int!) on FIELD

    directive @fold on FIELD

    type Animal implements Entity, UniquelyIdentifiable {
        _x_count: Int
        alias: [String]
        alive: Boolean
        birthday: Date
        color: String
        description: String
        in_Animal_ParentOf: [Animal]
        in_Entity_Related: [Entity]
        name: String
        net_worth: Decimal
        out_Animal_BornAt: [BirthEvent]
        out_Animal_FedAt: [FeedingEvent]
        out_Animal_ImportantEvent: [Union__BirthEvent__Event__FeedingEvent]
        out_Animal_LivesIn: [Location]
        out_Animal_OfSpecies: [Species]
        out_Animal_ParentOf: [Animal]
        out_Entity_Related: [Entity]
        uuid: ID
    }

    type BirthEvent implements Entity, UniquelyIdentifiable {
        _x_count: Int
        alias: [String]
        description: String
        event_date: DateTime
        in_Animal_BornAt: [Animal]
        in_Animal_ImportantEvent: [Animal]
        in_Entity_Related: [Entity]
        in_Event_RelatedEvent: [Union__BirthEvent__Event__FeedingEvent]
        name: String
        out_Entity_Related: [Entity]
        out_Event_RelatedEvent: [Union__BirthEvent__Event__FeedingEvent]
        uuid: ID
    }

    scalar Date

    scalar DateTime

    scalar Decimal

    interface Entity {
        _x_count: Int
        alias: [String]
        description: String
        in_Entity_Related: [Entity]
        name: String
        out_Entity_Related: [Entity]
        uuid: ID
    }

    type Event implements Entity, UniquelyIdentifiable {
        _x_count: Int
        alias: [String]
        description: String
        event_date: DateTime
        in_Animal_ImportantEvent: [Animal]
        in_Entity_Related: [Entity]
        in_Event_RelatedEvent: [Union__BirthEvent__Event__FeedingEvent]
        name: String
        out_Entity_Related: [Entity]
        out_Event_RelatedEvent: [Union__BirthEvent__Event__FeedingEvent]
        uuid: ID
    }

    type FeedingEvent implements Entity, UniquelyIdentifiable {
        _x_count: Int
        alias: [String]
        description: String
        event_date: DateTime
        in_Animal_FedAt: [Animal]
        in_Animal_ImportantEvent: [Animal]
        in_Entity_Related: [Entity]
        in_Event_RelatedEvent: [Union__BirthEvent__Event__FeedingEvent]
        name: String
        out_Entity_Related: [Entity]
        out_Event_RelatedEvent: [Union__BirthEvent__Event__FeedingEvent]
        uuid: ID
    }

    type Food implements Entity, UniquelyIdentifiable {
        _x_count: Int
        alias: [String]
        description: String
        in_Entity_Related: [Entity]
        in_Species_Eats: [Species]
        name: String
        out_Entity_Related: [Entity]
        uuid: ID
    }

    type FoodOrSpecies implements Entity, UniquelyIdentifiable {
        _x_count: Int
        alias: [String]
        description: String
        in_Entity_Related: [Entity]
        in_Species_Eats: [Species]
        name: String
        out_Entity_Related: [Entity]
        uuid: ID
    }

    type Location implements Entity, UniquelyIdentifiable {
        _x_count: Int
        alias: [String]
        description: String
        in_Animal_LivesIn: [Animal]
        in_Entity_Related: [Entity]
        name: String
        out_Entity_Related: [Entity]
        uuid: ID
    }

    type RootSchemaQuery {
        Animal: [Animal]
        BirthEvent: [BirthEvent]
        Entity: [Entity]
        Event: [Event]
        FeedingEvent: [FeedingEvent]
        Food: [Food]
        FoodOrSpecies: [FoodOrSpecies]
        Location: [Location]
        Species: [Species]
        UniquelyIdentifiable: [UniquelyIdentifiable]
    }

    type Species implements Entity, UniquelyIdentifiable {
        _x_count: Int
        alias: [String]
        description: String
        in_Animal_OfSpecies: [Animal]
        in_Entity_Related: [Entity]
        in_Species_Eats: [Species]
        limbs: Int
        name: String
        out_Entity_Related: [Entity]
        out_Species_Eats: [Union__Food__FoodOrSpecies__Species]
        uuid: ID
    }

    union Union__BirthEvent__Event__FeedingEvent = BirthEvent | Event | FeedingEvent

    union Union__Food__FoodOrSpecies__Species = Food | FoodOrSpecies | Species

    interface UniquelyIdentifiable {
        _x_count: Int
        uuid: ID
    }
'''


def transform(emitted_output):
    """Transform emitted_output into a unique representation, regardless of lines / indentation."""
    return WHITESPACE_PATTERN.sub(u'', emitted_output)


def _get_mismatch_message(expected_blocks, received_blocks):
    """Create a well-formated error message indicating that two lists of blocks are mismatched."""
    pretty_expected = pformat(expected_blocks)
    pretty_received = pformat(received_blocks)
    return u'{}\n\n!=\n\n{}'.format(pretty_expected, pretty_received)


def compare_ir_blocks(test_case, expected_blocks, received_blocks):
    """Compare the expected and received IR blocks."""
    mismatch_message = _get_mismatch_message(expected_blocks, received_blocks)

    if len(expected_blocks) != len(received_blocks):
        test_case.fail(u'Not the same number of blocks:\n\n'
                       u'{}'.format(mismatch_message))

    for i in six.moves.xrange(len(expected_blocks)):
        expected = expected_blocks[i]
        received = received_blocks[i]
        test_case.assertEqual(expected, received,
                              msg=u'Blocks at position {} were different: {} vs {}\n\n'
                                  u'{}'.format(i, expected, received, mismatch_message))


def compare_match(test_case, expected, received, parameterized=True):
    """Compare the expected and received MATCH code, ignoring whitespace."""
    msg = '\n{}\n\n!=\n\n{}'.format(
        pretty_print_match(expected, parameterized=parameterized),
        pretty_print_match(received, parameterized=parameterized))
    compare_ignoring_whitespace(test_case, expected, received, msg)


def compare_sql(test_case, expected, received):
    """Compare the expected and received SQL query, ignoring whitespace."""
    msg = '\n{}\n\n!=\n\n{}'.format(expected, received)
    compare_ignoring_whitespace(test_case, expected, received, msg)


def compare_gremlin(test_case, expected, received):
    """Compare the expected and received Gremlin code, ignoring whitespace."""
    msg = '\n{}\n\n!=\n\n{}'.format(
        pretty_print_gremlin(expected),
        pretty_print_gremlin(received))
    compare_ignoring_whitespace(test_case, expected, received, msg)


def compare_input_metadata(test_case, expected, received):
    """Compare two dicts of input metadata, using proper GraphQL type comparison operators."""
    # First, assert that the sets of keys in both dicts are equal.
    test_case.assertEqual(set(six.iterkeys(expected)), set(six.iterkeys(received)))

    # Then, compare the values for each key in both dicts.
    for key in six.iterkeys(expected):
        expected_value = expected[key]
        received_value = received[key]

        test_case.assertTrue(expected_value.is_same_type(received_value),
                             msg=u'{} != {}'.format(str(expected_value), str(received_value)))


def compare_ignoring_whitespace(test_case, expected, received, msg):
    """Compare expected and received code, ignoring whitespace, with the given failure message."""
    test_case.assertEqual(transform(expected), transform(received), msg=msg)


def get_schema():
    """Get a schema object for testing."""
    ast = parse(SCHEMA_TEXT)
    schema = build_ast_schema(ast)
    return schema


def get_sql_metadata():
    import sqlalchemy
    tables = {}
    sqlalchemy_metadata = sqlalchemy.MetaData()
    sqlalchemy_metadata.schema = 'Animals.schema_1'
    tables['Animal'] = sqlalchemy.Table(
        'Animal',
        sqlalchemy_metadata,
        sqlalchemy.Column('uuid', sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column('name', sqlalchemy.String(length=12), nullable=False),
        sqlalchemy.Column('net_worth', sqlalchemy.Integer, nullable=True),
        sqlalchemy.Column('birthday', sqlalchemy.Date, nullable=False),
        sqlalchemy.Column('alive', sqlalchemy.Boolean(), nullable=True),
        sqlalchemy.Column('parent', sqlalchemy.String(36), nullable=True),
        sqlalchemy.Column('species', sqlalchemy.String(36), nullable=True),
        sqlalchemy.Column('related_entity', sqlalchemy.String(36), nullable=True),
        sqlalchemy.Column('fed_at', sqlalchemy.String(36), nullable=True),
        sqlalchemy.Column('important_event', sqlalchemy.String(36), nullable=True),
    )
    tables['BirthEvent'] = sqlalchemy.Table(
        'BirthEvent',
        sqlalchemy_metadata,
        sqlalchemy.Column('uuid', sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column('name', sqlalchemy.String(length=12), nullable=False),
    )
    tables['Entity'] = sqlalchemy.Table(
        'Entity',
        sqlalchemy_metadata,
        sqlalchemy.Column('uuid', sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column('name', sqlalchemy.String(length=12), nullable=False),
        sqlalchemy.Column('related_entity', sqlalchemy.String(36), nullable=True),
        sqlalchemy.Column('__source_table_name', sqlalchemy.String(36), nullable=False),
    )
    tables['Event'] = sqlalchemy.Table(
        'Event',
        sqlalchemy_metadata,
        sqlalchemy_metadata,
        sqlalchemy.Column('uuid', sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column('event_date', sqlalchemy.DateTime, nullable=False),
    )
    tables['FeedingEvent'] = sqlalchemy.Table(
        'FeedingEvent',
        sqlalchemy_metadata,
        sqlalchemy.Column('uuid', sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column('name', sqlalchemy.String(length=12), nullable=False),
        sqlalchemy.Column('event_date', sqlalchemy.DateTime, nullable=False),
    )
    tables['Food'] = sqlalchemy.Table(
        'Food',
        sqlalchemy_metadata,
        sqlalchemy.Column('uuid', sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column('name', sqlalchemy.String(length=12), nullable=False),
    )
    tables['FoodOrSpecies'] = sqlalchemy.Table(
        'FoodOrSpecies',
        sqlalchemy_metadata,
        sqlalchemy.Column('uuid', sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column('name', sqlalchemy.String(length=12), nullable=False),
    )
    tables['Location'] = sqlalchemy.Table(
        'Location',
        sqlalchemy_metadata,
        sqlalchemy.Column('uuid', sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column('name', sqlalchemy.String(length=12), nullable=False),
    )
    tables['Species'] = sqlalchemy.Table(
        'Species',
        sqlalchemy_metadata,
        sqlalchemy.Column('uuid', sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column('name', sqlalchemy.String(length=12), nullable=False),
        sqlalchemy.Column('eats', sqlalchemy.String(36), nullable=True),
    )
    tables['UniquelyIdentifiable'] = sqlalchemy.Table(
        'UniquelyIdentifiable',
        sqlalchemy_metadata,
        sqlalchemy.Column('uuid', sqlalchemy.String(36), primary_key=True),
    )
    tables['Union__BirthEvent__Event__FeedingEvent'] = sqlalchemy.Table(
        'Union__BirthEvent__Event__FeedingEvent',
        sqlalchemy_metadata,
        sqlalchemy.Column('uuid', sqlalchemy.String(36), primary_key=True),
    )
    tables['Union__Food__FoodOrSpecies__Species'] = sqlalchemy.Table(
        'Union__Food__FoodOrSpecies__Species',
        sqlalchemy_metadata,
        sqlalchemy.Column('uuid', sqlalchemy.String(36), primary_key=True),
    )

    subclasses = {
        'Entity': {'Entity', 'Animal', 'Species', 'Event', 'Food'}
    }

    edges = {
        'Animal': {
            'out_Animal_ParentOf': {
                'to_table': 'Animal',
                'from_column': 'parent',
                'to_column': 'uuid',
            },
            'out_Animal_OfSpecies': {
                'to_table': 'Species',
                'from_column': 'species',
                'to_column': 'uuid',
            },
            'out_Animal_FedAt': {
                'to_table': 'FeedingEvent',
                'from_column': 'fed_at',
                'to_column': 'uuid',
            },
            'out_Animal_ImportantEvent': {
                'to_table': 'Union__BirthEvent__Event__FeedingEvent',
                'from_column': 'important_event',
                'to_column': 'uuid',
            },
        },
        'Species': {
            'out_Species_Eats': {
                'to_table': 'Union__Food__FoodOrSpecies__Species',
                'from_column': 'eats',
                'to_column': 'uuid',
            },
        },
        'Entity': {
            'out_Entity_Related': {
                # TODO this should be a junction table instead
                'to_table': 'Entity',
                'from_column': 'related_entity',
                'to_column': 'uuid',
            }
        }
    }

    # Include reversed edges
    reversed_edges = {}
    for class_name, out_edges in six.iteritems(edges):
        for edge_name, join_info in six.iteritems(out_edges):
            reversed_edge_name = 'in_{}'.format(edge_name[4:])
            reversed_edges.setdefault(join_info['to_table'], {})[reversed_edge_name] = {
                'to_table': class_name,
                'from_column': join_info['to_column'],
                'to_column': join_info['from_column'],
            }
    edges = {
        class_name: dict(edges.get(class_name, {}), **reversed_edges.get(class_name, {}))
        for class_name in tables.keys()
    }

    # Inherit edges from superclasses
    for class_name, subclass_set in six.iteritems(subclasses):
        for subclass in subclass_set:
            for edge_name, join_info in six.iteritems(edges[class_name]):
                edges.setdefault(subclass, {})[edge_name] = join_info

    return tables, edges



def generate_schema_graph(graph_client):
    """Generate SchemaGraph from a pyorient client"""
    schema_records = graph_client.command(ORIENTDB_SCHEMA_RECORDS_QUERY)
    schema_data = [x.oRecordData for x in schema_records]
    index_records = graph_client.command(ORIENTDB_INDEX_RECORDS_QUERY)
    index_query_data = [x.oRecordData for x in index_records]
    return get_orientdb_schema_graph(schema_data, index_query_data)


def generate_schema(graph_client, class_to_field_type_overrides=None, hidden_classes=None):
    """Generate schema and type equivalence dict from a pyorient client"""
    schema_records = graph_client.command(ORIENTDB_SCHEMA_RECORDS_QUERY)
    schema_data = [x.oRecordData for x in schema_records]
    return get_graphql_schema_from_orientdb_schema_data(schema_data, class_to_field_type_overrides,
                                                        hidden_classes)


def construct_location_types(location_types_as_strings):
    """Convert the supplied dict into a proper location_types dict with GraphQL types as values."""
    schema = get_schema()

    return {
        location: schema.get_type(type_name)
        for location, type_name in six.iteritems(location_types_as_strings)
    }
