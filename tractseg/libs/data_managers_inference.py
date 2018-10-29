#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2017 Division of Medical Image Computing, German Cancer Research Center (DKFZ)
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

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from builtins import object
import numpy as np

from tractseg.libs import exp_utils
from tractseg.libs.DLDABG_standalone import ZeroMeanUnitVarianceTransform as ZeroMeanUnitVarianceTransform_Standalone
from tractseg.libs.DLDABG_standalone import SingleThreadedAugmenter
from tractseg.libs.DLDABG_standalone import ReorderSegTransform
from tractseg.libs.DLDABG_standalone import Compose

np.random.seed(1337)  # for reproducibility

class DataLoader2D_data_ordered_standalone(object):
    '''
    Same as tractseg.libs.BatchGenerators.SlicesBatchGenerator, but does not depend on DKFZ/BatchGenerators package.
    Therefore good for inference on windows where DKFZ/Batchgenerators do not work (because of MultiThreading problems)
    '''
    def __init__(self, data, batch_size):
        # super(self.__class__, self).__init__(*args, **kwargs)
        self.Config = None
        self.batch_size = batch_size
        self.global_idx = 0
        self._data = data

    def __iter__(self):
        return self

    def __next__(self):
        return self.generate_train_batch()

    def generate_train_batch(self):
        if self.Config.SLICE_DIRECTION == "x":
            end = self._data[0].shape[0]
        elif self.Config.SLICE_DIRECTION == "y":
            end = self._data[0].shape[1]
        elif self.Config.SLICE_DIRECTION == "z":
            end = self._data[0].shape[2]

        # Stop iterating if we reached end of data
        if self.global_idx >= end:
            # print("Stopped because end of file")
            self.global_idx = 0
            raise StopIteration

        new_global_idx = self.global_idx + self.batch_size

        # If we reach end, make last batch smaller, so it fits exactly into rest
        if new_global_idx >= end:
            new_global_idx = end  # not end-1, because this goes into range, and there automatically -1

        idxs = list(range(self.global_idx, new_global_idx))

        if self.Config.SLICE_DIRECTION == "x":
            x = np.array(self._data[0][idxs,:,:,:]).astype(np.float32)
            y = np.array(self._data[1][idxs,:,:,:]).astype(self.Config.LABELS_TYPE)
            x = x.transpose(0, 3, 1, 2)  # depth-channel has to be before width and height for Unet (but after batches)
            y = y.transpose(0, 3, 1, 2)  # nr_classes channel has to be before with and height for DataAugmentation (bs, nr_of_classes, x, y)
        elif self.Config.SLICE_DIRECTION == "y":
            x = np.array(self._data[0][:,idxs,:,:]).astype(np.float32)
            y = np.array(self._data[1][:,idxs,:,:]).astype(self.Config.LABELS_TYPE)
            x = x.transpose(1, 3, 0, 2)  # depth-channel has to be before width and height for Unet (but after batches)
            y = y.transpose(1, 3, 0, 2)  # nr_classes channel has to be before with and height for DataAugmentation (bs, nr_of_classes, x, y)
        elif self.Config.SLICE_DIRECTION == "z":
            x = np.array(self._data[0][:,:,idxs,:]).astype(np.float32)
            y = np.array(self._data[1][:,:,idxs,:]).astype(self.Config.LABELS_TYPE)
            x = x.transpose(2, 3, 0, 1)  # depth-channel has to be before width and height for Unet (but after batches)
            y = y.transpose(2, 3, 0, 1)  # nr_classes channel has to be before with and height for DataAugmentation (bs, nr_of_classes, x, y)

        data_dict = {"data": x,     # (batch_size, channels, x, y, [z])
                     "seg": y}      # (batch_size, channels, x, y, [z])
        self.global_idx = new_global_idx
        return data_dict

class DataManagerSingleSubjectByFile:
    def __init__(self, Config, data):
        self.data = data
        self.Config = Config
        exp_utils.print_verbose(self.Config, "Loading data from PREDICT_IMG input file")

    def get_batches(self, batch_size=1):
        data = np.nan_to_num(self.data)
        # Use dummy mask in case we only want to predict on some data (where we do not have Ground Truth))
        seg = np.zeros((self.Config.INPUT_DIM[0], self.Config.INPUT_DIM[0], self.Config.INPUT_DIM[0], self.Config.NR_OF_CLASSES)).astype(self.Config.LABELS_TYPE)

        num_processes = 1  # not not use more than 1 if you want to keep original slice order (Threads do return in random order)
        batch_gen = DataLoader2D_data_ordered_standalone((data, seg), batch_size=batch_size)
        batch_gen.Config = self.Config
        tfs = []  # transforms

        if self.Config.NORMALIZE_DATA:
            tfs.append(ZeroMeanUnitVarianceTransform_Standalone(per_channel=self.Config.NORMALIZE_PER_CHANNEL))
        tfs.append(ReorderSegTransform())
        batch_gen = SingleThreadedAugmenter(batch_gen, Compose(tfs))
        return batch_gen  # data: (batch_size, channels, x, y), seg: (batch_size, x, y, channels)
