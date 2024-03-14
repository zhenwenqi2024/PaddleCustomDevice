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

# install lcov
wget -P /home https://paddle-ci.cdn.bcebos.com/coverage/lcov-1.16.tar.gz --no-proxy --no-check-certificate || exit 101
tar -xf /home/lcov-1.16.tar.gz -C /
cd /lcov-1.16
make install

cd ${CODE_ROOT}/build

lcov --ignore-errors gcov --capture -d ./ -o coverage.info --rc lcov_branch_coverage=0

function gen_full_html_report() {
    lcov --extract coverage.info \
        '/paddle/backends/npu/custom_op/*' \
        '/paddle/backends/npu/kernels/*' \
        '/paddle/backends/npu/runtime/*' \
        -o coverage-full.tmp \
        --rc lcov_branch_coverage=0

    mv -f coverage-full.tmp coverage-full.info
}

gen_full_html_report

genhtml coverage-full.info --output-directory cpp-coverage-full
