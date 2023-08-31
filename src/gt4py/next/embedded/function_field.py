# GT4Py - GridTools Framework
#
# Copyright (c) 2014-2023, ETH Zurich
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

from __future__ import annotations

import dataclasses
import operator
from typing import Callable, TypeAlias, Any

import numpy as np

from gt4py._core import definitions as core_defs
from gt4py.next import common
from gt4py.next.common import Infinity
from gt4py.next.embedded import common as embedded_common, nd_array_field as nd
from gt4py.next.embedded.nd_array_field import _get_slices_from_domain_slice

_EMPTY_DOMAIN = common.Domain((), ())

ConstantFieldValue: TypeAlias = int | float | complex


@dataclasses.dataclass(frozen=True)
class FunctionField:
    func: Callable
    domain: common.Domain = _EMPTY_DOMAIN
    _constant: bool = False

    def restrict(self, index: common.FieldSlice) -> common.Field | core_defs.ScalarT:
        if _has_empty_domain(self):
            raise IndexError("Cannot slice ConstantField without a Domain.")
        new_domain = embedded_common.sub_domain(self.domain, index)
        return self.__class__(self.func, new_domain)

    __getitem__ = restrict

    @property
    def ndarray(self) -> core_defs.NDArrayObject:
        if _has_empty_domain(self):
            raise ValueError("Cannot get ndarray for FunctionField without Domain.")

        shape = []
        for _, rng in self.domain:
            if Infinity.positive() in (abs(rng.start), abs(rng.stop)):
                raise ValueError(
                    f"Cannot construct ndarray with infinite range in Domain: {self.domain}"
                )
            else:
                shape.append(len(rng))

        if self._constant:
            return np.full(shape, self.func())

        return np.fromfunction(lambda *indices: self.func(*indices), shape)

    def _handle_identity_op(self, other: FunctionField, operator_func: Callable) -> FunctionField:
        domain_intersection = self.domain & other.domain
        broadcasted_self = _broadcast(self, domain_intersection.dims)
        broadcasted_other = _broadcast(other, domain_intersection.dims)
        return self.__class__(
            _compose(operator_func, broadcasted_self, broadcasted_other), domain_intersection
        )

    def _binary_op_wrapper(self, other: FunctionFieldOperand, op: Callable) -> FunctionFieldOperand:
        if _is_nd_array(other):
            if _has_empty_domain(self):
                return self._handle_empty_domain_op(other, op)
            else:
                return self._handle_non_empty_domain_op(other, op)
        elif isinstance(other, self.__class__):
            return self._handle_identity_op(other, op)
        else:
            raise ValueError(
                f"Unsupported type in binary operation between {self.__class__} and {other.__class__}"
            )

    def _handle_empty_domain_op(
        self, other: nd._BaseNdArrayField, op: Callable
    ) -> nd._BaseNdArrayField:
        self_broadcasted = self.__class__(self.func, other.domain)
        new_data = op(self_broadcasted.ndarray, other.ndarray)
        return other.__class__.from_array(new_data, domain=other.domain)

    def _handle_non_empty_domain_op(
        self, other: nd._BaseNdArrayField, op: Callable
    ) -> nd._BaseNdArrayField:
        domain_intersection = self.domain & other.domain
        self_broadcasted = self.__class__(self.func, domain_intersection)
        other_broadcasted = nd._broadcast(other, domain_intersection.dims)
        other_slices = _get_slices_from_domain_slice(other_broadcasted.domain, domain_intersection)
        new_data = op(self_broadcasted.ndarray, other_broadcasted.ndarray[other_slices])
        return other.__class__.from_array(new_data, domain=domain_intersection)

    def _binary_operation(self, op: Callable, other: FunctionFieldOperand) -> FunctionFieldOperand:
        if _is_nd_array(other):
            if _has_empty_domain(self):
                return self._handle_empty_domain_op(other, op)
            else:
                return self._handle_non_empty_domain_op(other, op)
        elif isinstance(other, self.__class__):
            return self._handle_identity_op(other, op)
        else:
            raise ValueError(
                f"Unsupported type in binary operation between {self.__class__} and {other.__class__}"
            )

    def __add__(self, other: FunctionFieldOperand) -> FunctionFieldOperand:
        return self._binary_operation(operator.add, other)

    def __sub__(self, other: FunctionFieldOperand) -> FunctionFieldOperand:
        return self._binary_operation(operator.sub, other)

    def __mul__(self, other: FunctionFieldOperand) -> FunctionFieldOperand:
        return self._binary_operation(operator.mul, other)

    def __truediv__(self, other: FunctionFieldOperand) -> FunctionFieldOperand:
        return self._binary_operation(operator.truediv, other)

    def __floordiv__(self, other: FunctionFieldOperand) -> FunctionFieldOperand:
        return self._binary_operation(operator.floordiv, other)

    def __mod__(self, other: FunctionFieldOperand) -> FunctionFieldOperand:
        return self._binary_operation(operator.mod, other)

    def __pow__(self, other: FunctionFieldOperand) -> FunctionFieldOperand:
        return self._binary_operation(operator.pow, other)

    def __eq__(self, other: FunctionFieldOperand) -> FunctionFieldOperand:
        return self._binary_operation(operator.eq, other)

    def __ne__(self, other: FunctionFieldOperand) -> FunctionFieldOperand:
        return self._binary_operation(operator.ne, other)

    def __lt__(self, other: FunctionFieldOperand) -> FunctionFieldOperand:
        return self._binary_operation(operator.lt, other)

    def __le__(self, other: FunctionFieldOperand) -> FunctionFieldOperand:
        return self._binary_operation(operator.le, other)

    def __gt__(self, other: FunctionFieldOperand) -> FunctionFieldOperand:
        return self._binary_operation(operator.gt, other)

    def __ge__(self, other: FunctionFieldOperand) -> FunctionFieldOperand:
        return self._binary_operation(operator.ge, other)

    def __pos__(self) -> FunctionField:
        return self.__class__(_compose(operator.pos, self), self.domain)

    def __neg__(self) -> FunctionField:
        return self.__class__(_compose(operator.neg, self), self.domain)

    def __invert__(self) -> FunctionField:
        return self.__class__(_compose(operator.invert, self), self.domain)

    def __abs__(self) -> FunctionField:
        return self.__class__(_compose(abs, self), self.domain)

    def __call__(self, *args, **kwargs) -> None:
        raise NotImplementedError()

    def remap(self, *args, **kwargs) -> None:
        raise NotImplementedError()


FunctionFieldOperand: TypeAlias = FunctionField | nd._BaseNdArrayField


def _compose(operation: Callable, *fields: FunctionField) -> Callable:
    return lambda *args: operation(*[f.func(*args) for f in fields])


def _broadcast(field: FunctionField, dims: tuple[common.Dimension]) -> FunctionField:
    def broadcasted_function(*args: int):
        if not _has_empty_domain(field):
            selected_args = [args[i] for i, dim in enumerate(dims) if dim in field.domain.dims]
            return field.func(*selected_args)
        return field.func(*args)

    broadcasted_domain = common.Domain(
        dims=dims, ranges=tuple([common.UnitRange.infinity()] * len(dims))
    )

    return FunctionField(broadcasted_function, broadcasted_domain)


def _is_nd_array(other: Any) -> bool:
    return isinstance(other, nd._BaseNdArrayField)


def _has_empty_domain(field: FunctionField) -> bool:
    return len(field.domain) < 1


def constant_field(
    value: ConstantFieldValue, domain: common.Domain = _EMPTY_DOMAIN
) -> FunctionField:
    return FunctionField(lambda *args: value, domain, _constant=True)
