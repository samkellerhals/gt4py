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

from typing import Optional
from gt4py.next import common
from gt4py.next.errors import exceptions as gt4py_exceptions


class IndexOutOfBounds(gt4py_exceptions.GT4PyError):
    domain: common.Domain
    indices: common.AnyIndexSpec
    index: Optional[common.AnyIndexElement]
    dim: Optional[common.Dimension]

    def __init__(
        self,
        domain: common.Domain,
        indices: common.AnyIndexSpec,
        index: Optional[common.AnyIndexElement] = None,
        dim: Optional[common.Dimension] = None,
    ):
        msg = f"Out of bounds: slicing {domain} with index `{indices}`."
        if index is not None and dim is not None:
            msg += f" `{index}` is out of bounds in dimension `{dim}`."

        super().__init__(msg)
        self.domain = domain
        self.indices = indices
        self.index = index
        self.dim = dim


class EmptyDomainIndexError(gt4py_exceptions.GT4PyError):
    index: common.AnyIndexSpec

    def __init__(self, cls_name: str):
        super().__init__(f"Error in `{cls_name}`: Cannot index `{cls_name}` with an empty domain.")
        self.cls_name = cls_name


class InvalidDomainForNdarrayError(gt4py_exceptions.GT4PyError):
    def __init__(self, cls_name: str):
        super().__init__(
            f"Error in `{cls_name}`: Cannot construct an ndarray with an empty domain."
        )
        self.cls_name = cls_name


class InfiniteRangeNdarrayError(gt4py_exceptions.GT4PyError):
    def __init__(self, cls_name: str, domain: common.Domain):
        super().__init__(
            f"Error in `{cls_name}`: Cannot construct an ndarray with an infinite range in domain: `{domain}`."
        )
        self.cls_name = cls_name
        self.domain = domain
