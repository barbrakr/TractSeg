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

import importlib
import argparse
import pickle
import warnings
import time
from pprint import pprint
import distutils.util
from os.path import join
import nibabel as nib
import numpy as np

from tractseg.libs.DatasetUtils import DatasetUtils
from tractseg.libs.DirectionMerger import DirectionMerger
from tractseg.libs.ExpUtils import ExpUtils
from tractseg.libs.ImgUtils import ImgUtils
from tractseg.libs.MetricUtils import MetricUtils
from tractseg.libs.Config import Config as C
from tractseg.libs.Trainer import Trainer

'''
Adapt for 32g_25mm prediction:
- DATASET=HCP_32g
- FEATURES_FILENAME=32g_25mm_peaks
- 32g_25mm_peaks not available on new Cluster at the moment
'''

warnings.simplefilter("ignore", UserWarning)    #hide scipy warnings

#Settings and Hyperparameters
class HP:
    EXP_MULTI_NAME = ""              #CV Parent Dir name # leave empty for Single Bundle Experiment
    EXP_NAME = "HCP_TEST"       # HCP_normAfter
    MODEL = "UNet_Pytorch"     # UNet_Lasagne / UNet_Pytorch
    NUM_EPOCHS = 500
    DATA_AUGMENTATION = True
    DAUG_INFO = "Elastic(90,120)(9,11) - Scale(0.9, 1.5) - CenterDist60 - DownsampScipy(0.5,1) - Contrast(0.7,1.3) - Gaussian(0,0.05) - BrightnessMult(0.7,1.3) - RotateUltimate(-0.8,0.8) - Mirror"
    DATASET = "HCP"  # HCP / HCP_32g
    RESOLUTION = "1.25mm"  # 1.25mm (/ 2.5mm)
    FEATURES_FILENAME = "270g_125mm_peaks"  # 270g_125mm_xyz / 270g_125mm_peaks / 90g_125mm_peaks / 32g_25mm_peaks / 32g_25mm_xyz
    LABELS_FILENAME = "bundle_masks"     # bundle_masks / bundle_masks_45       #Only used when using DataManagerNifti
    DATASET_FOLDER = "HCP"  # HCP / TRACED / HCP_fusion_npy_270g_125mm / HCP_fusion_npy_32g_25mm
    LABELS_FOLDER = "bundle_masks"  # bundle_masks / bundle_masks_dm
    MULTI_PARENT_PATH = join(C.EXP_PATH, EXP_MULTI_NAME)
    EXP_PATH = join(C.EXP_PATH, EXP_MULTI_NAME, EXP_NAME)  # default path
    BATCH_SIZE = 46  # Lasagne: 56  # Lasagne combined: 42   #Pytorch: 46
    LEARNING_RATE = 0.002
    UNET_NR_FILT = 64
    LOAD_WEIGHTS = False
    # WEIGHTS_PATH = join(C.EXP_PATH, "HCP100_45B_UNet_x_DM_lr002_slope2_dec992_ep800/best_weights_ep64.npz")    # Can be absolute path or relative like "exp_folder/weights.npz"
    WEIGHTS_PATH = ""   # if empty string: autoloading the best_weights in get_best_weights_path()
    TYPE = "single_direction"       # single_direction / combined
    CV_FOLD = 0
    VALIDATE_SUBJECTS = []
    TRAIN_SUBJECTS = []
    TEST_SUBJECTS = []
    TRAIN = True
    TEST = True  # python ExpRunner.py --train=False --seg=False --test=True --lw=True
    SEGMENT = False
    GET_PROBS = False  # python ExpRunner.py --train=False --seg=False --probs=True --lw=True

    # PREDICT_IMG = False
    # PREDICT_IMG_OUTPUT = None
    OUTPUT_MULTIPLE_FILES = False
    # TRACTSEG_DIR = "tractseg_output"
    # KEEP_INTERMEDIATE_FILES = False
    # CSD_RESOLUTION = "LOW"  # HIGH / LOW

    #Unimportant / rarly changed:
    LABELS_TYPE = np.int16  # Binary: np.int16, Regression: np.float32
    THRESHOLD = 0.5  # Binary: 0.5, Regression: 0.01 ?
    TEST_TIME_DAUG = False
    SLICE_DIRECTION = "x"  #no effect at the moment     # x, y, z  (combined needs z)
    USE_VISLOGGER = False
    INFO = "74 BNew, DMNifti, newSplit, 90gAnd270g, NormBeforeDAug, Fusion: 32gAnd270g"
    SAVE_WEIGHTS = True
    NR_OF_CLASSES = len(ExpUtils.get_bundle_names())
    SEG_INPUT = "Peaks"     # Gradients/ Peaks
    NR_SLICES = 1           # adapt manually: NR_OF_GRADIENTS in UNet.py and get_batch... in train() and in get_seg_prediction()
    PRINT_FREQ = 20
    NORMALIZE_DATA = True
    BEST_EPOCH = 0
    INPUT_DIM = (144, 144)
    VERBOSE = True

parser = argparse.ArgumentParser(description="Train a network on your own data to segment white matter bundles.",
                                    epilog="Written by Jakob Wasserthal. Please reference TODO")
parser.add_argument("--train", metavar="True/False", help="Train network", type=distutils.util.strtobool, default=True)
parser.add_argument("--test", metavar="True/False", help="Test network", type=distutils.util.strtobool, default=True)
parser.add_argument("--seg", action="store_true", help="Create binary segmentation", default=False)   #todo: better API
parser.add_argument("--probs", action="store_true", help="Create probmap segmentation", default=False)   #todo: better API
parser.add_argument("--lw", action="store_true", help="Load weights of pretrained net", default=False)   #todo: better API
parser.add_argument("--en", metavar="name", help="Experiment name")
parser.add_argument("--fold", metavar="N", help="Which fold to train when doing CrossValidation", type=int, default=0)
parser.add_argument("--verbose", action="store_true", help="Show more intermediate output", default=True) #todo: set default to false
parser.add_argument('--version', action='version', version='TractSeg 0.5')
args = parser.parse_args()

if args.en:
    HP.EXP_NAME = args.en

HP.TRAIN = bool(args.train)
HP.TEST = bool(args.test)
HP.SEGMENT = args.seg
HP.GET_PROBS = args.probs
HP.LOAD_WEIGHTS = args.lw
HP.CV_FOLD= args.fold
HP.VERBOSE = args.verbose

HP.MULTI_PARENT_PATH = join(C.EXP_PATH, HP.EXP_MULTI_NAME)
HP.EXP_PATH = join(C.EXP_PATH, HP.EXP_MULTI_NAME, HP.EXP_NAME)
HP.TRAIN_SUBJECTS, HP.VALIDATE_SUBJECTS, HP.TEST_SUBJECTS = ExpUtils.get_cv_fold(HP.CV_FOLD)

if HP.VERBOSE:
    print("Hyperparameters:")
    ExpUtils.print_HPs(HP)

if HP.TRAIN:
    HP.EXP_PATH = ExpUtils.create_experiment_folder(HP.EXP_NAME, HP.MULTI_PARENT_PATH, HP.TRAIN)

DataManagerSingleSubjectById = getattr(importlib.import_module("tractseg.libs." + "DataManagers"), "DataManagerSingleSubjectById")
DataManagerTraining = getattr(importlib.import_module("tractseg.libs." + "DataManagers"), "DataManagerTrainingNiftiImgs")

def test_whole_subject(HP, model, subjects, type):

    metrics = {
        "loss_" + type: [0],
        "f1_macro_" + type: [0],
    }

    # Metrics per bundle
    metrics_bundles = {}
    for bundle in ExpUtils.get_bundle_names():
        metrics_bundles[bundle] = [0]

    for subject in subjects:
        print("{} subject {}".format(type, subject))
        start_time = time.time()

        dataManagerSingle = DataManagerSingleSubjectById(HP, subject=subject)
        trainerSingle = Trainer(model, dataManagerSingle)
        img_probs, img_y = trainerSingle.get_seg_single_img(HP, probs=True)
        # img_probs_xyz, img_y = DirectionMerger.get_seg_single_img_3_directions(HP, model, subject=subject)
        # igm_probs = DirectionMerger.mean_fusion(HP.THRESHOLD, img_probs_xyz, probs=True)

        print("Took {}s".format(round(time.time() - start_time, 2)))

        img_probs = np.reshape(img_probs, (-1, img_probs.shape[-1]))  #Flatten all dims except nrClasses dim
        img_y = np.reshape(img_y, (-1, img_y.shape[-1]))

        metrics = MetricUtils.calculate_metrics(metrics, img_y, img_probs, 0, type=type, threshold=HP.THRESHOLD)
        metrics_bundles = MetricUtils.calculate_metrics_each_bundle(metrics_bundles, img_y, img_probs, ExpUtils.get_bundle_names(), threshold=HP.THRESHOLD)

    metrics = MetricUtils.normalize_last_element(metrics, len(subjects), type=type)
    metrics_bundles = MetricUtils.normalize_last_element_general(metrics_bundles, len(subjects))

    print("WHOLE SUBJECT:")
    pprint(metrics)
    print("WHOLE SUBJECT BUNDLES:")
    pprint(metrics_bundles)


    with open(join(HP.EXP_PATH, "score_" + type + "-set.txt"), "w") as f:
        pprint(metrics, f)
        f.write("\n\nWeights: {}\n".format(HP.WEIGHTS_PATH))
        f.write("type: {}\n\n".format(type))
        pprint(metrics_bundles, f)

    pickle.dump(metrics, open(join(HP.EXP_PATH, "score_" + type + ".pkl"), "wb"))

    return metrics


dataManager = DataManagerTraining(HP)
ModelClass = getattr(importlib.import_module("tractseg.models." + HP.MODEL), HP.MODEL)
model = ModelClass(HP)
trainer = Trainer(model, dataManager)

if HP.TRAIN:
    print("Training...")
    metrics = trainer.train(HP)

#After Training
if HP.TRAIN:
    # have to load other weights, because after training it has the weights of the last epoch
    print("Loading best epoch: {}".format(HP.BEST_EPOCH))
    HP.WEIGHTS_PATH = HP.EXP_PATH + "/best_weights_ep" + str(HP.BEST_EPOCH) + ".npz"
    HP.LOAD_WEIGHTS = True
    trainer.model.load_model(join(HP.EXP_PATH, HP.WEIGHTS_PATH))
    model_test = trainer.model
else:
    # Weight_path already set to best model (wenn reading program parameters) -> will be loaded automatically
    model_test = trainer.model

if HP.SEGMENT:
    ExpUtils.make_dir(join(HP.EXP_PATH, "segmentations"))
    # all_subjects = HP.VALIDATE_SUBJECTS #+ HP.TEST_SUBJECTS
    all_subjects = HP.TEST_SUBJECTS
    for subject in all_subjects:
        print("Get_segmentation subject {}".format(subject))
        start_time = time.time()

        dataManagerSingle = DataManagerSingleSubjectById(HP, subject=subject, use_gt_mask=False)
        trainerSingle = Trainer(model_test, dataManagerSingle)
        img_seg, img_y = trainerSingle.get_seg_single_img(HP, probs=False)  # only x or y or z
        # img_seg, img_y = DirectionMerger.get_seg_single_img_3_directions(HP, model, subject)  #returns probs not binary seg

        # ImgUtils.save_multilabel_img_as_multiple_files(HP, img_seg, subject)   # Save as several files
        img = nib.Nifti1Image(img_seg, ImgUtils.get_dwi_affine(HP.DATASET, HP.RESOLUTION))
        nib.save(img, join(HP.EXP_PATH, "segmentations", subject + "_segmentation.nii.gz"))
        print("took {}s".format(time.time() - start_time))

if HP.TEST:
    test_whole_subject(HP, model_test, HP.VALIDATE_SUBJECTS, "validate")
    test_whole_subject(HP, model_test, HP.TEST_SUBJECTS, "test")

if HP.GET_PROBS:
    ExpUtils.make_dir(join(HP.EXP_PATH, "probmaps"))
    # ExpUtils.make_dir(join(HP.EXP_PATH, "probmaps_32g_25mm"))
    all_subjects = HP.TEST_SUBJECTS
    # all_subjects = HP.TRAIN_SUBJECTS + HP.VALIDATE_SUBJECTS + HP.TEST_SUBJECTS
    for subject in all_subjects:
        print("Get_probs subject {}".format(subject))

        # dataManagerSingle = DataManagerSingleSubjectById(HP, subject=subject, use_gt_mask=False)
        # trainerSingle = Trainer(model_test, dataManagerSingle)
        # img_probs, img_y = trainerSingle.get_seg_single_img(HP, probs=True)
        img_probs, img_y = DirectionMerger.get_seg_single_img_3_directions(HP, model, subject=subject)

        #Save as one probmap for further combined training
        img = nib.Nifti1Image(img_probs, ImgUtils.get_dwi_affine(HP.DATASET, HP.RESOLUTION))
        nib.save(img, join(HP.EXP_PATH, "probmaps", subject + "_probmap.nii.gz"))
