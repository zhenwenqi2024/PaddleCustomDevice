# Copyright (c) 2022 PaddlePaddle Authors. All Rights Reserved.
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
from __future__ import print_function

import unittest
import numpy as np
import paddle
import paddle.nn as nn
import paddle.base.core as core
import paddle.base as base

from tests.op_test import OpTest

paddle.enable_static()


def conv2dtranspose_forward_naive(input_, filter_, attrs):
    padding_algorithm = attrs["padding_algorithm"]
    if padding_algorithm not in ["SAME", "VALID", "EXPLICIT"]:
        raise ValueError(
            "Unknown Attr(padding_algorithm): '%s'. "
            "It can only be 'SAME' or 'VALID'." % str(padding_algorithm)
        )

    if attrs["data_format"] == "NHWC":
        input_ = np.transpose(input_, [0, 3, 1, 2])
    in_n, in_c, in_h, in_w = input_.shape
    f_c, f_out_c, f_h, f_w = filter_.shape
    groups = attrs["groups"]
    assert in_c == f_c
    out_c = f_out_c * groups
    sub_in_c = in_c // groups

    stride, pad, dilations = attrs["strides"], attrs["paddings"], attrs["dilations"]

    # update pad and dilation
    def _get_padding_with_SAME(input_shape, kernel_size, kernel_stride):
        padding = []
        for input_size, filter_size, stride_size in zip(
            input_shape, kernel_size, kernel_stride
        ):
            out_size = int((input_size + stride_size - 1) / stride_size)
            pad_sum = np.max(
                ((out_size - 1) * stride_size + filter_size - input_size, 0)
            )
            pad_0 = int(pad_sum / 2)
            pad_1 = int(pad_sum - pad_0)
            padding.append(pad_0)
            padding.append(pad_1)
        return padding

    ksize = filter_.shape[2:4]
    if padding_algorithm == "VALID":
        pad = [0, 0, 0, 0]
    elif padding_algorithm == "SAME":
        dilations = [1, 1]
        input_data_shape = input_.shape[2:4]
        pad = _get_padding_with_SAME(input_data_shape, ksize, stride)

    pad_h_0, pad_h_1 = pad[0], pad[0]
    pad_w_0, pad_w_1 = pad[1], pad[1]
    if len(pad) == 4:
        pad_h_0, pad_h_1 = pad[0], pad[1]
        pad_w_0, pad_w_1 = pad[2], pad[3]

    d_bolck_h = dilations[0] * (f_h - 1) + 1
    d_bolck_w = dilations[1] * (f_w - 1) + 1
    out_h = (in_h - 1) * stride[0] + d_bolck_h
    out_w = (in_w - 1) * stride[1] + d_bolck_w
    if "output_size" in attrs:
        output_size = attrs["output_size"]
        out_h = output_size[0] + pad_h_0 + pad_h_1
        out_w = output_size[1] + pad_w_0 + pad_w_1
    out_pad_h = 0
    out_pad_w = 0
    if "output_padding" in attrs:
        out_pad_h = attrs["output_padding"][0]
        out_pad_w = attrs["output_padding"][1]
    out = np.zeros(
        (in_n, out_c, out_h + out_pad_h, out_w + out_pad_w), dtype=input_.dtype
    )

    for n in range(in_n):
        for i in range(in_h):
            for j in range(in_w):
                for g in range(groups):
                    input_masked = input_[
                        n, g * sub_in_c : (g + 1) * sub_in_c, i, j
                    ]  # (c)
                    input_masked = np.reshape(input_masked, (sub_in_c, 1, 1))
                    input_masked = np.tile(input_masked, (1, f_h, f_w))

                    for k in range(f_out_c):
                        tmp_out = np.sum(
                            input_masked
                            * filter_[g * sub_in_c : (g + 1) * sub_in_c, k, :, :],
                            axis=0,
                        )
                        i1, i2 = i * stride[0], i * stride[0] + d_bolck_h
                        j1, j2 = j * stride[1], j * stride[1] + d_bolck_w
                        out[
                            n,
                            g * f_out_c + k,
                            i1 : i2 : dilations[0],
                            j1 : j2 : dilations[1],
                        ] += tmp_out

    out = out[
        :,
        :,
        pad_h_0 : out_h - pad_h_1 + out_pad_h,
        pad_w_0 : out_w - pad_w_1 + out_pad_w,
    ]
    if attrs["data_format"] == "NHWC":
        out = np.transpose(out, [0, 2, 3, 1])
    return out


class TestConv2DTransposeOp(OpTest):
    def set_npu(self):
        self.__class__.use_custom_device = True
        self.place = paddle.CustomPlace("npu", 0)

    def setUp(self):
        # init as conv transpose
        self.set_npu()
        self.dtype = np.float32
        self.need_check_grad = True
        self.is_test = False
        self.output_size = None
        self.output_padding = []
        self.data_format = "NCHW"
        self.pad = [0, 0]
        self.padding_algorithm = "EXPLICIT"
        self.init_op_type()
        self.init_test_case()
        self.init_dtype()

        input_ = np.random.random(self.input_size).astype(self.dtype)
        filter_ = np.random.random(self.filter_size).astype(self.dtype)

        self.inputs = {"Input": input_, "Filter": filter_}
        self.attrs = {
            "strides": self.stride,
            "paddings": self.pad,
            "padding_algorithm": self.padding_algorithm,
            "groups": self.groups,
            "dilations": self.dilations,
            "use_cudnn": False,
            "is_test": False,
            "use_mkldnn": False,
            "data_format": self.data_format,
        }
        if self.output_size is not None:
            self.attrs["output_size"] = self.output_size

        if len(self.output_padding) > 0:
            self.attrs["output_padding"] = self.output_padding
        output = conv2dtranspose_forward_naive(input_, filter_, self.attrs).astype(
            self.dtype
        )

        self.outputs = {"Output": output}

    def test_check_output(self):
        self.check_output_with_place(self.place, atol=1e-2)

    def test_check_grad_no_input(self):
        if self.need_check_grad:
            self.check_grad_with_place(
                self.place,
                ["Filter"],
                "Output",
                no_grad_set=set(["Input"]),
                numeric_place=paddle.CPUPlace(),
            )

    def test_check_grad_no_filter(self):
        if self.need_check_grad:
            self.check_grad_with_place(
                self.place,
                ["Input"],
                "Output",
                no_grad_set=set(["Filter"]),
                max_relative_error=0.006,
                numeric_place=paddle.CPUPlace(),
            )

    def test_check_grad(self):
        if self.need_check_grad:
            self.check_grad_with_place(
                self.place,
                set(["Input", "Filter"]),
                "Output",
                max_relative_error=0.02,
                numeric_place=paddle.CPUPlace(),
            )

    def init_test_case(self):
        self.pad = [0, 0]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 1
        self.input_size = [2, 3, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 3, 3]

    def init_op_type(self):
        self.op_type = "conv2d_transpose"

    def init_dtype(self):
        self.dtype = np.float32


class TestWithSymmetricPad(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 1
        self.input_size = [2, 3, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 3, 3]


class TestWithSymmetricPad_FP16(TestWithSymmetricPad):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithAsymmetricPad(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 0, 1, 2]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 1
        self.input_size = [2, 3, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 3, 3]


class TestWithAsymmetricPad_FP16(TestWithAsymmetricPad):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithSAMEPad(TestConv2DTransposeOp):
    def init_test_case(self):
        self.stride = [2, 1]
        self.dilations = [1, 2]
        self.groups = 1
        self.input_size = [2, 3, 6, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 4, 3]
        self.padding_algorithm = "SAME"


class TestWithSAMEPad_FP16(TestWithSAMEPad):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithVALIDPad(TestConv2DTransposeOp):
    def init_test_case(self):
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 1
        self.input_size = [2, 3, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 3, 3]
        self.padding_algorithm = "VALID"


class TestWithVALIDPad_FP16(TestWithVALIDPad):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithGroups(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 2
        self.input_size = [2, 4, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 3, 3, 3]


class TestWithGroups_FP16(TestWithGroups):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithStride(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [2, 2]
        self.dilations = [1, 1]
        self.groups = 1
        self.input_size = [2, 3, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 3, 3]


class TestWithStride_FP16(TestWithStride):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithDilation(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [1, 1]
        self.groups = 1
        self.dilations = [2, 2]
        self.input_size = [2, 3, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 3, 3]


class TestWithDilation_FP16(TestWithDilation):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithEvenUpsample(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [2, 2]
        self.stride = [2, 2]
        self.groups = 1
        self.dilations = [1, 1]
        self.output_size = [14, 14]
        self.input_size = [2, 3, 7, 7]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 5, 5]


class TestWithEvenUpsample_FP16(TestWithEvenUpsample):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithEvenUpsampleOutputPadding(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [2, 2]
        self.stride = [2, 2]
        self.groups = 1
        self.dilations = [1, 1]
        self.output_padding = [1, 1]
        self.input_size = [2, 3, 7, 7]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 5, 5]


class TestWithEvenUpsampleOutputPadding_FP16(TestWithEvenUpsampleOutputPadding):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class Test_NHWC(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [0, 0]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 1
        self.input_size = [2, 5, 5, 3]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 3, 3]
        self.data_format = "NHWC"


class Test_NHWC_FP16(Test_NHWC):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithSymmetricPad_NHWC(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 1
        self.input_size = [2, 5, 5, 3]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 3, 3]
        self.data_format = "NHWC"


class TestWithSymmetricPad_NHWC_FP16(TestWithSymmetricPad_NHWC):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithAsymmetricPad_NHWC(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 0, 1, 2]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 1
        self.input_size = [2, 5, 5, 3]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 3, 3]
        self.data_format = "NHWC"


class TestWithAsymmetricPad_NHWC_FP16(TestWithAsymmetricPad_NHWC):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithGroups_NHWC(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 2
        self.input_size = [2, 5, 5, 4]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 3, 3, 3]
        self.data_format = "NHWC"


class TestWithGroups_NHWC_FP16(TestWithGroups_NHWC):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithStride_NHWC(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [2, 2]
        self.dilations = [1, 1]
        self.groups = 1
        self.input_size = [2, 5, 5, 3]  # NCHW
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 3, 3]
        self.data_format = "NHWC"


class TestWithStride_NHWC_FP16(TestWithStride_NHWC):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithDilation_NHWC(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [1, 1]
        self.groups = 1
        self.dilations = [2, 2]
        self.input_size = [2, 5, 5, 3]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 3, 3]
        self.data_format = "NHWC"


class TestWithDilation_NHWC_FP16(TestWithDilation_NHWC):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithEvenUpsample_NHWC(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [2, 2]
        self.stride = [2, 2]
        self.groups = 1
        self.dilations = [1, 1]
        self.output_size = [14, 14]
        self.input_size = [2, 7, 7, 3]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 5, 5]
        self.data_format = "NHWC"


class TestWithEvenUpsample_NHWC_FP16(TestWithEvenUpsample_NHWC):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithEvenUpsample_NHWC_output_padding(TestConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [2, 2]
        self.stride = [2, 2]
        self.groups = 1
        self.dilations = [1, 1]
        self.output_padding = [1, 1]
        self.input_size = [2, 7, 7, 3]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 5, 5]
        self.data_format = "NHWC"


class TestWithEvenUpsample_NHWC_output_padding_FP16(
    TestWithEvenUpsample_NHWC_output_padding
):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestConv2DTransposeAPI(unittest.TestCase):
    def test_case1(self):
        data1 = paddle.static.data(name="data1", shape=[-1, 3, 5, 5], dtype="float32")
        data2 = paddle.static.data(name="data2", shape=[-1, 5, 5, 3], dtype="float32")
        out1 = paddle.static.nn.conv2d_transpose(
            input=data1, groups=1, num_filters=6, filter_size=3, data_format="NCHW"
        )
        out2 = paddle.static.nn.conv2d_transpose(
            input=data2, groups=1, num_filters=6, filter_size=3, data_format="NHWC"
        )
        out3 = paddle.static.nn.conv2d_transpose(
            input=data1,
            groups=1,
            num_filters=6,
            filter_size=3,
            padding=[[0, 0], [1, 1], [1, 1], [0, 0]],
            data_format="NHWC",
        )
        out4 = paddle.static.nn.conv2d_transpose(
            input=data1,
            groups=3,
            num_filters=6,
            filter_size=3,
            padding=[[0, 0], [0, 0], [2, 1], [0, 0]],
            data_format="NCHW",
        )
        out5 = paddle.static.nn.conv2d_transpose(
            input=data2,
            groups=1,
            num_filters=6,
            filter_size=3,
            padding="SAME",
            data_format="NCHW",
        )
        out6 = paddle.static.nn.conv2d_transpose(
            input=data1,
            groups=1,
            num_filters=6,
            filter_size=3,
            padding="VALID",
            data_format="NHWC",
        )
        out7 = paddle.static.nn.conv2d_transpose(
            input=data1,
            groups=1,
            num_filters=6,
            output_size=[7, 7],
            padding=[0, 0],
            data_format="NHWC",
        )

        data1_np = np.random.random((2, 3, 5, 5)).astype("float32")
        data2_np = np.random.random((2, 5, 5, 3)).astype("float32")

        place = core.CustomPlace("npu", 0)
        exe = base.Executor(place)
        exe.run(base.default_startup_program())
        results = exe.run(
            base.default_main_program(),
            feed={"data1": data1_np, "data2": data2_np},
            fetch_list=[out1, out2, out3, out4, out5, out6, out7],
            return_numpy=True,
        )
        self.assertIsNotNone(results[0])
        self.assertIsNotNone(results[1])
        self.assertIsNotNone(results[2])
        self.assertIsNotNone(results[3])
        self.assertIsNotNone(results[4])
        self.assertIsNotNone(results[5])
        self.assertIsNotNone(results[6])


class TestConv2DTransposeRepr(unittest.TestCase):
    def test_case(self):
        paddle.disable_static(paddle.CustomPlace("npu", 0))
        x_var = paddle.uniform((2, 4, 8, 8), dtype="float32", min=-1.0, max=1.0)
        conv = nn.Conv2DTranspose(4, 6, (3, 3), output_padding=1, stride=2)
        print(conv)
        y_var = conv(x_var)
        y_np = y_var.numpy()
        self.assertIsNotNone(y_np)
        paddle.enable_static()


class TestDepthwiseConv2DTransposeOp(OpTest):
    def set_npu(self):
        self.__class__.use_custom_device = True
        self.place = paddle.CustomPlace("npu", 0)

    def setUp(self):
        # init as conv transpose
        self.set_npu()
        self.dtype = np.float32
        self.need_check_grad = True
        self.is_test = False
        self.output_size = None
        self.output_padding = []
        self.data_format = "NCHW"
        self.pad = [0, 0]
        self.padding_algorithm = "EXPLICIT"
        self.init_op_type()
        self.init_test_case()
        self.init_dtype()

        input_ = np.random.random(self.input_size).astype(self.dtype)
        filter_ = np.random.random(self.filter_size).astype(self.dtype)

        self.inputs = {"Input": input_, "Filter": filter_}
        self.attrs = {
            "strides": self.stride,
            "paddings": self.pad,
            "padding_algorithm": self.padding_algorithm,
            "groups": self.groups,
            "dilations": self.dilations,
            "use_cudnn": False,
            "is_test": False,
            "use_mkldnn": False,
            "data_format": self.data_format,
        }
        if self.output_size is not None:
            self.attrs["output_size"] = self.output_size

        if len(self.output_padding) > 0:
            self.attrs["output_padding"] = self.output_padding
        output = conv2dtranspose_forward_naive(input_, filter_, self.attrs).astype(
            self.dtype
        )

        self.outputs = {"Output": output}

    def test_check_output(self):
        self.check_output_with_place(self.place, atol=1e-2)

    def test_check_grad_no_input(self):
        if self.need_check_grad:
            self.check_grad_with_place(
                self.place,
                ["Filter"],
                "Output",
                no_grad_set=set(["Input"]),
                numeric_place=paddle.CPUPlace(),
            )

    def test_check_grad_no_filter(self):
        if self.need_check_grad:
            self.check_grad_with_place(
                self.place,
                ["Input"],
                "Output",
                no_grad_set=set(["Filter"]),
                max_relative_error=0.006,
                numeric_place=paddle.CPUPlace(),
            )

    def test_check_grad(self):
        if self.need_check_grad:
            self.check_grad_with_place(
                self.place,
                set(["Input", "Filter"]),
                "Output",
                max_relative_error=0.02,
                numeric_place=paddle.CPUPlace(),
            )

    def init_test_case(self):
        self.pad = [0, 0]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 3
        self.input_size = [2, 3, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 3, 3]

    def init_op_type(self):
        self.op_type = "depthwise_conv2d_transpose"

    def init_dtype(self):
        self.dtype = np.float32


class TestWithSymmetricPad_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 3
        self.input_size = [2, 3, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 3, 3]


class TestWithSymmetricPad_FP16_Depthwise(TestWithSymmetricPad_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithAsymmetricPad_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 0, 1, 2]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 3
        self.input_size = [2, 3, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 3, 3]


class TestWithAsymmetricPad_FP16_Depthwise(TestWithAsymmetricPad_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithSAMEPad_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.stride = [2, 1]
        self.dilations = [1, 2]
        self.groups = 3
        self.input_size = [2, 3, 6, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 4, 3]
        self.padding_algorithm = "SAME"


class TestWithSAMEPad_FP16_Depthwise(TestWithSAMEPad_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithVALIDPad_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 3
        self.input_size = [2, 3, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 3, 3]
        self.padding_algorithm = "VALID"


class TestWithVALIDPad_FP16_Depthwise(TestWithVALIDPad_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithGroups_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 4
        self.input_size = [2, 4, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 3, 3, 3]


class TestWithGroups_FP16_Depthwise(TestWithGroups_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithStride_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [2, 2]
        self.dilations = [1, 1]
        self.groups = 3
        self.input_size = [2, 3, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 3, 3]


class TestWithStride_FP16_Depthwise(TestWithStride_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithDilation_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [1, 1]
        self.groups = 3
        self.dilations = [2, 2]
        self.input_size = [2, 3, 5, 5]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 3, 3]


class TestWithDilation_FP16_Depthwise(TestWithDilation_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithEvenUpsample_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [2, 2]
        self.stride = [2, 2]
        self.groups = 3
        self.dilations = [1, 1]
        self.output_size = [14, 14]
        self.input_size = [2, 3, 7, 7]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 5, 5]


class TestWithEvenUpsample_FP16_Depthwise(TestWithEvenUpsample_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithEvenUpsampleOutputPadding_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [2, 2]
        self.stride = [2, 2]
        self.groups = 3
        self.dilations = [1, 1]
        self.output_padding = [1, 1]
        self.input_size = [2, 3, 7, 7]  # NCHW
        f_c = self.input_size[1]
        self.filter_size = [f_c, 6, 5, 5]


class TestWithEvenUpsampleOutputPadding_FP16_Depthwise(
    TestWithEvenUpsampleOutputPadding_Depthwise
):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class Test_NHWC_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [0, 0]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 3
        self.input_size = [2, 5, 5, 3]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 3, 3]
        self.data_format = "NHWC"


class Test_NHWC_FP16_Depthwise(Test_NHWC_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithSymmetricPad_NHWC_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 3
        self.input_size = [2, 5, 5, 3]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 3, 3]
        self.data_format = "NHWC"


class TestWithSymmetricPad_NHWC_FP16_Depthwise(TestWithSymmetricPad_NHWC_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithAsymmetricPad_NHWC_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 0, 1, 2]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 3
        self.input_size = [2, 5, 5, 3]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 3, 3]
        self.data_format = "NHWC"


class TestWithAsymmetricPad_NHWC_FP16_Depthwise(TestWithAsymmetricPad_NHWC_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithGroups_NHWC_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [1, 1]
        self.dilations = [1, 1]
        self.groups = 4
        self.input_size = [2, 5, 5, 4]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 3, 3, 3]
        self.data_format = "NHWC"


class TestWithGroups_NHWC_FP16_Depthwise(TestWithGroups_NHWC_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithStride_NHWC_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [2, 2]
        self.dilations = [1, 1]
        self.groups = 3
        self.input_size = [2, 5, 5, 3]  # NCHW
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 3, 3]
        self.data_format = "NHWC"


class TestWithStride_NHWC_FP16_Depthwise(TestWithStride_NHWC_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithDilation_NHWC_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [1, 1]
        self.stride = [1, 1]
        self.groups = 3
        self.dilations = [2, 2]
        self.input_size = [2, 5, 5, 3]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 3, 3]
        self.data_format = "NHWC"


class TestWithDilation_NHWC_FP16_Depthwise(TestWithDilation_NHWC_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithEvenUpsample_NHWC_Depthwise(TestDepthwiseConv2DTransposeOp):
    def init_test_case(self):
        self.pad = [2, 2]
        self.stride = [2, 2]
        self.groups = 3
        self.dilations = [1, 1]
        self.output_size = [14, 14]
        self.input_size = [2, 7, 7, 3]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 5, 5]
        self.data_format = "NHWC"


class TestWithEvenUpsample_NHWC_FP16_Depthwise(TestWithEvenUpsample_NHWC_Depthwise):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestWithEvenUpsample_NHWC_output_padding_Depthwise(
    TestDepthwiseConv2DTransposeOp
):
    def init_test_case(self):
        self.pad = [2, 2]
        self.stride = [2, 2]
        self.groups = 3
        self.dilations = [1, 1]
        self.output_padding = [1, 1]
        self.input_size = [2, 7, 7, 3]  # NHWC
        f_c = self.input_size[-1]
        self.filter_size = [f_c, 6, 5, 5]
        self.data_format = "NHWC"


class TestWithEvenUpsample_NHWC_output_padding_FP16_Depthwise(
    TestWithEvenUpsample_NHWC_output_padding_Depthwise
):
    def init_dtype(self):
        self.dtype = np.float16
        self.need_check_grad = False


class TestConv2DTransposeAPI(unittest.TestCase):
    def test_case1(self):
        data1 = paddle.static.data(name="data1", shape=[-1, 3, 5, 5], dtype="float32")
        data2 = paddle.static.data(name="data2", shape=[-1, 5, 5, 3], dtype="float32")
        out1 = paddle.static.nn.conv2d_transpose(
            input=data1, groups=3, num_filters=6, filter_size=3, data_format="NCHW"
        )
        out2 = paddle.static.nn.conv2d_transpose(
            input=data2, groups=3, num_filters=6, filter_size=3, data_format="NHWC"
        )
        out3 = paddle.static.nn.conv2d_transpose(
            input=data1,
            groups=5,
            num_filters=6,
            filter_size=3,
            padding=[[0, 0], [1, 1], [1, 1], [0, 0]],
            data_format="NHWC",
        )
        out4 = paddle.static.nn.conv2d_transpose(
            input=data1,
            groups=3,
            num_filters=6,
            filter_size=3,
            padding=[[0, 0], [0, 0], [2, 1], [0, 0]],
            data_format="NCHW",
        )
        out5 = paddle.static.nn.conv2d_transpose(
            input=data2,
            groups=5,
            num_filters=6,
            filter_size=3,
            padding="SAME",
            data_format="NCHW",
        )
        out6 = paddle.static.nn.conv2d_transpose(
            input=data1,
            groups=5,
            num_filters=6,
            filter_size=3,
            padding="VALID",
            data_format="NHWC",
        )
        out7 = paddle.static.nn.conv2d_transpose(
            input=data1,
            groups=5,
            num_filters=6,
            output_size=[7, 7],
            padding=[0, 0],
            data_format="NHWC",
        )

        data1_np = np.random.random((2, 3, 5, 5)).astype("float32")
        data2_np = np.random.random((2, 5, 5, 3)).astype("float32")

        place = core.CustomPlace("npu", 0)
        exe = base.Executor(place)
        exe.run(base.default_startup_program())
        results = exe.run(
            base.default_main_program(),
            feed={"data1": data1_np, "data2": data2_np},
            fetch_list=[out1, out2, out3, out4, out5, out6, out7],
            return_numpy=True,
        )
        self.assertIsNotNone(results[0])
        self.assertIsNotNone(results[1])
        self.assertIsNotNone(results[2])
        self.assertIsNotNone(results[3])
        self.assertIsNotNone(results[4])
        self.assertIsNotNone(results[5])
        self.assertIsNotNone(results[6])


if __name__ == "__main__":
    unittest.main()
