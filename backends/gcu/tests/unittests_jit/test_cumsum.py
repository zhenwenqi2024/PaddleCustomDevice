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

test = ApiBase(
    func=paddle.cumsum, feed_names=["data"], feed_shapes=[[3, 4]], is_train=False
)


@pytest.mark.cumsum
@pytest.mark.filterwarnings("ignore::UserWarning")
def test_cumsum1():
    data = np.arange(0, 12, dtype=np.float32).reshape((3, 4))
    test.run(feed=[data], dtype="int32")


@pytest.mark.cumsum
@pytest.mark.filterwarnings("ignore::UserWarning")
def test_cumsum2():
    data = np.random.randn(3, 4).astype("float32")
    test.run(feed=[data], axis=1, dtype="float32")


@pytest.mark.cumsum
@pytest.mark.filterwarnings("ignore::UserWarning")
def test_cumsum3():
    data = np.random.randn(3, 4).astype("float32")
    test.run(feed=[data], axis=0)


paddle.enable_static()
np.random.seed(33)
main_program = paddle.static.Program()
startup_program = paddle.static.Program()
main_program.random_seed = 33
startup_program.random_seed = 33


@pytest.mark.cumsum
@pytest.mark.filterwarnings("ignore::UserWarning")
def test_cumsum4():
    with paddle.utils.unique_name.guard():
        with paddle.static.program_guard(
            main_program=main_program, startup_program=startup_program
        ):
            data = paddle.static.data(name="data", shape=[2, 19], dtype="int64")
            data.stop_gradient = True
            out = paddle.cumsum(data, dtype="int64", axis=-1)
            fetch_list = [out.name]
            print(main_program)
            print("start to debug run")
            exe = paddle.static.Executor("gcu:0")
            x = np.arange(0, 38, dtype=np.int64).reshape((2, 19)).astype("int64")
            output_dtu = exe.run(
                main_program, feed={"data": x}, fetch_list=fetch_list, return_numpy=True
            )
            exec = paddle.static.Executor(paddle.CPUPlace())
            exec.run(startup_program)
            output_cpu = exec.run(
                main_program, feed={"data": x}, fetch_list=fetch_list, return_numpy=True
            )
            print("output num:", len(output_dtu))
            for i in range(len(output_dtu)):
                print("------------")
                print(np.allclose(output_dtu[i], output_cpu[i], atol=1e-5, rtol=1e-5))
                print(fetch_list[i], output_dtu[i].reshape(-1))
                print(fetch_list[i], output_cpu[i].reshape(-1))


from paddle.base.layer_helper import LayerHelper


def my_cumsum(input, axis, flatten=False, exclusive=False, reverse=False, name=None):
    helper = LayerHelper("cumsum", **locals())
    inputs = {"X": input}
    attrs = {
        "axis": axis,
        "flatten": flatten,
        "exclusive": exclusive,
        "reverse": reverse,
    }

    out = helper.create_variable_for_type_inference(dtype=input.dtype)
    helper.append_op(type="cumsum", inputs=inputs, attrs=attrs, outputs={"Out": out})

    return out


@pytest.mark.cumsum
@pytest.mark.filterwarnings("ignore::UserWarning")
def test_cumsum5():
    data = np.random.randn(1, 3, 4, 4).astype("float32")
    obj = ApiBase(
        func=my_cumsum, feed_names=["data"], feed_shapes=[[1, 3, 4, 4]], is_train=False
    )
    obj.run(feed=[data], axis=1)


@pytest.mark.cumsum
@pytest.mark.filterwarnings("ignore::UserWarning")
def test_cumsum6():
    data = np.random.randn(1, 3, 4, 4).astype("float32")
    obj = ApiBase(
        func=my_cumsum, feed_names=["data"], feed_shapes=[[1, 3, 4, 4]], is_train=False
    )
    obj.run(feed=[data], axis=1, exclusive=True)


@pytest.mark.cumsum
@pytest.mark.filterwarnings("ignore::UserWarning")
def test_cumsum7():
    data = np.random.randn(1, 3, 4, 4).astype("float32")
    obj = ApiBase(
        func=my_cumsum, feed_names=["data"], feed_shapes=[[1, 3, 4, 4]], is_train=False
    )
    obj.run(feed=[data], axis=1, exclusive=True, reverse=True)


@pytest.mark.cumsum
@pytest.mark.filterwarnings("ignore::UserWarning")
def test_cumsum8():
    data = np.random.randn(1, 3, 4, 4).astype("float32")
    obj = ApiBase(
        func=my_cumsum, feed_names=["data"], feed_shapes=[[1, 3, 4, 4]], is_train=False
    )
    obj.run(feed=[data], axis=-1, exclusive=True, reverse=True, flatten=True)
