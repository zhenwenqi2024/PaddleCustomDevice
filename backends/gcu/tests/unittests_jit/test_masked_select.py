# Copyright (c) 2024 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from api_base import ApiBase
import paddle
import pytest
import numpy as np

test1 = ApiBase(
    func=paddle.masked_select,
    feed_names=["data", "mask"],
    feed_dtypes=["float32", "bool"],
    is_train=False,
    feed_shapes=[[3, 4], [3, 4]],
    threshold=1.0e-5,
)


@pytest.mark.masked_select
@pytest.mark.filterwarnings("ignore::UserWarning")
def test_masked_select():
    data = np.array([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]).astype("float32")
    mask = np.array(
        [
            [True, False, False, False],
            [True, True, False, False],
            [True, False, False, False],
        ]
    ).astype("bool")
    test1.run(feed=[data, mask])


test_masked_select()
