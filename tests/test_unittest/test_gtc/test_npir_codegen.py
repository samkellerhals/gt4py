# -*- coding: utf-8 -*-
#
# GTC Toolchain - GT4Py Project - GridTools Framework
#
# Copyright (c) 2014-2021, ETH Zurich
# All rights reserved.
#
# This file is part of the GT4Py project and the GridTools framework.
# GT4Py is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or any later
# version. See the LICENSE.txt file at the top-level directory of this
# distribution for a copy of the license or check <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re
import sys
from typing import Iterator, Optional, Set

import numpy as np
import pytest

from gtc import common
from gtc.numpy import npir
from gtc.numpy.npir_codegen import NpirCodegen

from .npir_utils import (
    ComputationFactory,
    FieldDeclFactory,
    FieldSliceFactory,
    HorizontalBlockFactory,
    LocalScalarAccessFactory,
    NativeFuncCallFactory,
    ParamAccessFactory,
    ScalarDeclFactory,
    TemporaryDeclFactory,
    VectorArithmeticFactory,
    VectorAssignFactory,
    VerticalPassFactory,
)


UNDEFINED_DTYPES = {common.DataType.INVALID, common.DataType.AUTO, common.DataType.DEFAULT}

DEFINED_DTYPES: Set[common.DataType] = set(common.DataType) - UNDEFINED_DTYPES  # type: ignore


@pytest.fixture(params=DEFINED_DTYPES)
def defined_dtype(request) -> Iterator[common.DataType]:
    yield request.param


@pytest.fixture()
def other_dtype(defined_dtype) -> Iterator[Optional[common.DataType]]:
    other = None
    for dtype in DEFINED_DTYPES:
        if dtype != defined_dtype:
            other = dtype
            break
    yield other


@pytest.fixture(params=[True, False])
def is_serial(request):
    yield request.param


def test_datatype() -> None:
    result = NpirCodegen().visit(common.DataType.FLOAT64)
    print(result)
    match = re.match(r"np.float64", result)
    assert match


def test_scalarliteral(defined_dtype: common.DataType) -> None:
    result = NpirCodegen().visit(npir.ScalarLiteral(dtype=defined_dtype, value="42"))
    print(result)
    match = re.match(r"np.(\w*?)\(42\)", result)
    assert match
    assert match.groups()[0] == defined_dtype.name.lower()


def test_broadcast_literal(defined_dtype: common.DataType, is_serial: bool) -> None:
    result = NpirCodegen().visit(
        npir.Broadcast(expr=npir.ScalarLiteral(dtype=defined_dtype, value="42")),
        is_serial=is_serial,
        lower=(0, 0),
        upper=(0, 0),
    )
    print(result)
    match = re.match(
        r"np\.full\(\(_dI_\s*\+\s*(?P<iext>\d+)\s*,\s*_dJ_\s*\+\s*(?P<jext>\d+)\s*,\s*(?P<kbounds>[^\)]+)\),\s*np\.(?P<dtype>\w+)\(42\)\)",
        result,
    )
    assert match
    assert tuple(match.group(ext) for ext in ("iext", "jext")) == ("0", "0")
    assert match.group("kbounds") == "1" if is_serial else "K - k"
    assert match.group("dtype") == defined_dtype.name.lower()


def test_scalar_cast(defined_dtype: common.DataType, other_dtype: common.DataType) -> None:
    result = NpirCodegen().visit(
        npir.ScalarCast(dtype=other_dtype, expr=npir.ScalarLiteral(dtype=defined_dtype, value="42"))
    )
    print(result)
    match = re.match(r"np\.(?P<other_dtype>\w*)\(np.(?P<defined_dtype>\w*)\(42\)\)", result)
    assert match
    assert match.group("defined_dtype") == defined_dtype.name.lower()
    assert match.group("other_dtype") == other_dtype.name.lower()


def test_vector_cast(defined_dtype: common.DataType, other_dtype: common.DataType) -> None:
    result = NpirCodegen().visit(
        npir.VectorCast(
            dtype=other_dtype,
            expr=npir.FieldSlice(name="a", i_offset=0, j_offset=0, k_offset=0, dtype=defined_dtype),
        )
    )
    print(result)
    match = re.match(r"(?P<name>\w+)\[.*]\.astype\(np\.(?P<dtype>\w+)\)", result)
    assert match
    assert match.group("name") == "a"
    assert match.group("dtype") == other_dtype.name.lower()


def test_field_slice(is_serial: bool) -> None:
    i_offset = 0
    j_offset = -2
    k_offset = 4

    def int_to_str(i):
        if i > 0:
            return "+" + str(i)
        elif i == 0:
            return ""
        else:
            return str(i)

    field_slice = FieldSliceFactory(
        name="a",
        i_offset=i_offset,
        j_offset=j_offset,
        k_offset=k_offset,
        dtype=common.DataType.INT32,
    )
    result = NpirCodegen().visit(field_slice, is_serial=is_serial)
    print(result)
    match = re.match(
        r"(?P<name>\w+)\[i(?P<il>.*):I(?P<iu>.*),\s*j(?P<jl>.*):J(?P<ju>.*),\s*(?P<kl>.*):(?P<ku>.*)\]",
        result,
    )
    assert match
    assert match.group("name") == "a"
    assert match.group("il") == match.group("iu") == int_to_str(i_offset)
    assert match.group("jl") == match.group("ju") == int_to_str(j_offset)

    if is_serial:
        assert match.group("kl") == "k_" + int_to_str(k_offset)
        assert match.group("ku") == "k_" + int_to_str(k_offset + 1)
    else:
        assert match.group("kl") == "k" + int_to_str(k_offset)
        assert match.group("ku") == "K" + int_to_str(k_offset)


def test_native_function() -> None:
    result = NpirCodegen().visit(
        NativeFuncCallFactory(
            func=common.NativeFunction.MIN,
            args=[
                FieldSliceFactory(name="a"),
                ParamAccessFactory(name="p"),
            ],
        )
    )
    print(result)
    match = re.match(r"np.minimum\(a\[.*\],\s*p\)", result)
    assert match


@pytest.mark.parametrize(
    "left", (FieldSliceFactory(name="left"), LocalScalarAccessFactory(name="left"))
)
def test_vector_assign(left, is_serial: bool) -> None:
    result = NpirCodegen().visit(
        VectorAssignFactory(left=left, right=FieldSliceFactory(name="right")),
        ctx=NpirCodegen.BlockContext(),
        is_serial=is_serial,
    )
    left_str, right_str = result.split(" = ")

    k_str = "k_:k_+1" if is_serial else "k:K"

    if isinstance(left, npir.FieldSlice):
        assert left_str == "left[i:I, j:J, " + k_str + "]"
    else:
        assert left_str == "left"

    assert right_str == "right[i:I, j:J, " + k_str + "]"


def test_field_definition() -> None:
    result = NpirCodegen().visit(FieldDeclFactory(name="a", dimensions=(True, True, False)))
    print(result)
    assert result == "a = Field(a, _origin_['a'], (True, True, False))"


def test_temp_definition() -> None:
    result = NpirCodegen().visit(TemporaryDeclFactory(name="a", offset=(1, 2), padding=(3, 4)))
    print(result)
    assert result == "a = Field.empty((_dI_ + 3, _dJ_ + 4, _dK_), (1, 2, 0))"


def test_vector_arithmetic() -> None:
    result = NpirCodegen().visit(
        npir.VectorArithmetic(
            left=FieldSliceFactory(name="a"),
            right=FieldSliceFactory(name="b"),
            op=common.ArithmeticOperator.ADD,
        ),
        is_serial=False,
    )
    assert result == "(a[i:I, j:J, k:K] + b[i:I, j:J, k:K])"


def test_vector_unary_op() -> None:
    result = NpirCodegen().visit(
        npir.VectorUnaryOp(
            expr=FieldSliceFactory(name="a"),
            op=common.UnaryOperator.NEG,
        ),
        is_serial=False,
    )
    assert result == "(-(a[i:I, j:J, k:K]))"


def test_vector_unary_not() -> None:
    result = NpirCodegen().visit(
        npir.VectorUnaryOp(
            op=common.UnaryOperator.NOT,
            expr=FieldSliceFactory(name="mask", dtype=common.DataType.BOOL),
        )
    )
    assert result == "(np.bitwise_not(mask[i:I, j:J, k:K]))"


def test_assign_with_mask_local() -> None:
    result = NpirCodegen().visit(
        VectorAssignFactory(
            left=LocalScalarAccessFactory(name="tmp"),
            mask=FieldSliceFactory(name="mask1", dtype=common.DataType.BOOL),
        ),
        ctx=NpirCodegen.BlockContext(),
        symtable={"tmp": ScalarDeclFactory(name="tmp", dtype=common.DataType.INT32)},
    )
    print(result)
    assert re.match(r"tmp = np.where\(mask1.*, np.int32\(\)\)", result) is not None


def test_horizontal_block() -> None:
    result = NpirCodegen().visit(HorizontalBlockFactory()).strip("\n")
    print(result)
    match = re.match(
        r"#.*\n" r"i, I = _di_ - 0, _dI_ \+ 0\n" r"j, J = _dj_ - 0, _dJ_ \+ 0\n",
        result,
        re.MULTILINE,
    )
    assert match


def test_vertical_pass_seq() -> None:
    result = NpirCodegen().visit(
        VerticalPassFactory(
            lower=common.AxisBound.from_start(offset=1),
            upper=common.AxisBound.from_end(offset=-2),
            direction=common.LoopOrder.FORWARD,
        )
    )
    print(result)
    match = re.match(
        (r"#.*\n" r"+k, K = _dk_ \+ 1, _dK_ - 2\n" r"for k_ in range\(k, K\):\n"),
        result,
        re.MULTILINE,
    )
    assert match


def test_vertical_pass_par() -> None:
    result = NpirCodegen().visit(VerticalPassFactory(direction=common.LoopOrder.PARALLEL))
    print(result)
    match = re.match(
        (r"(#.*?\n)?" r"k, K = _dk_, _dK_\n"),
        result,
        re.MULTILINE,
    )
    assert match


def test_computation() -> None:
    result = NpirCodegen().visit(
        ComputationFactory(
            vertical_passes__0__body__0__body__0=VectorAssignFactory(
                left__name="a", right__name="b"
            )
        )
    )
    print(result)
    match = re.match(
        (
            r"import numbers\n"
            r"from typing import Tuple\n+"
            r"import numpy as np\n"
            r"import scipy.special\n+"
            r"class Field:\n"
            r"(.*\n)+"
            r"def run\(\*, a, b, _domain_, _origin_\):\n"
            r"\n?"
            r"(    .*?\n)*"
        ),
        result,
        re.MULTILINE,
    )
    assert match


def test_full_computation_valid(tmp_path) -> None:
    computation = ComputationFactory(
        vertical_passes__0__body__0__body__0=VectorAssignFactory(
            left__name="a",
            right=VectorArithmeticFactory(
                left__name="b", right=ParamAccessFactory(name="p"), op=common.ArithmeticOperator.ADD
            ),
        ),
        param_decls=[ScalarDeclFactory(name="p")],
    )
    result = NpirCodegen().visit(computation)
    print(result)
    mod_path = tmp_path / "npir_codegen_1.py"
    mod_path.write_text(result)

    sys.path.append(str(tmp_path))
    import npir_codegen_1 as mod

    a = np.zeros((10, 10, 10))
    b = np.ones_like(a) * 3
    p = 2
    mod.run(
        a=a,
        b=b,
        p=p,
        _domain_=(8, 5, 9),
        _origin_={"a": (1, 1, 0), "b": (0, 0, 0)},
    )
    assert (a[1:9, 1:6, 0:9] == 5).all()