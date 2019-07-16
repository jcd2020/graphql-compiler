# Copyright 2018-present Kensho Technologies, LLC.
from ..ir_lowering_common.common import (extract_optional_location_root_info,
                                         extract_simple_optional_location_info,
                                         lower_context_field_existence,
                                         merge_consecutive_filter_clauses,
                                         optimize_boolean_expression_comparisons,
                                         remove_end_optionals)


def lower_ir(ir_blocks, query_metadata_table, type_equivalence_hints=None):
    ir_blocks = lower_context_field_existence(ir_blocks, query_metadata_table)
    return ir_blocks
