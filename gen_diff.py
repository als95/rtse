'''
usage: python gen_diff.py -h
'''

from __future__ import print_function

import argparse

from configs import bcolors
from utils import *
import numpy as np

from Model import WordPreprocessor, WordVecModeler
from Trainer_model1 import Trainer1
from Trainer_model2 import Trainer2
from Trainer_model3 import Trainer3

import tensorflow as tf
from keras.layers import Input
from keras.utils import to_categorical

from random import *

# read the parameter
# argument parsing
parser = argparse.ArgumentParser(
    description='Main function for difference-inducing input generation in ImageNet dataset')
parser.add_argument('transformation', help="realistic transformation type", choices=['synonym'])
parser.add_argument('weight_diff', help="weight hyperparm to control differential behavior", default = 1, type=float)
parser.add_argument('weight_nc', help="weight hyperparm to control neuron coverage", default = 0.1, type=float)
parser.add_argument('step', help="step size of gradient descent", default = 10, type=float)
parser.add_argument('seeds', help="number of seeds of input", type=int)
parser.add_argument('grad_iterations', help="number of iterations of gradient descent", type=int)
parser.add_argument('threshold', help="threshold for determining neuron activated", default = 0, type=float)
parser.add_argument('coverage', help="coverage option", choices=['dxp', 'kmnc', 'nbc', 'snbc'])
parser.add_argument('test_generation', help="test generation", choices=['dxp', 'fgsm'])

parser.add_argument('-t', '--target_model', help="target model that we want it predicts differently",
                    choices=[0, 1, 2], default=0, type=int)

args = parser.parse_args()

word_dim = 50
sum_vec = 1
word_preprocessor = WordPreprocessor()
raw_x = word_preprocessor.data_preprocessing('input/desc.txt')
assign_file = codecs.open('input/assignTo.txt', "r", "utf-8")
TB_SUMMARY_DIR = './onlycnn/add1/filter512/234/relu'

raw_y = []
for line in assign_file:
    line = line.strip()
    raw_y.append(line)
# load data end
le = preprocessing.LabelEncoder()
enc = preprocessing.OneHotEncoder()
le.fit(raw_y)
assign_num = len(set(raw_y))
y_to_number = np.array(le.transform(raw_y))
y_to_number = np.reshape(y_to_number, [-1, 1])
enc.fit(y_to_number)
one_hot_y = enc.transform(y_to_number).toarray()
# assign one_hot incoding

vec_x, resize_vec = data_preprocess(raw_x)
train_vec_x, train_one_hot_y = data_train(vec_x, resize_vec, one_hot_y)
test_vec_x, test_one_hot_y = data_test(vec_x, resize_vec, one_hot_y)

test_percent = 0.1
raw_x = raw_x[int(len(vec_x) * (1 - test_percent)):]

# load multiple models sharing same input tensor
model1_model = Trainer1(assign_size = assign_num
                        , word_dim = word_dim
                        , max_word_size = 500 / sum_vec
                        , TB_SUMMARY_DIR = TB_SUMMARY_DIR, filter = 512)
model2_model = Trainer2(assign_size = assign_num
                        , word_dim = word_dim
                        , max_word_size = 500 / sum_vec
                        , TB_SUMMARY_DIR = TB_SUMMARY_DIR, filter = 512)
model3_model = Trainer3(assign_size = assign_num
                        , word_dim = word_dim
                        , max_word_size = 500 / sum_vec
                        , TB_SUMMARY_DIR = TB_SUMMARY_DIR, filter = 512)

model1_model.train_learning()
model2_model.train_learning()
model3_model.train_learning()

model1 = model1_model.model
model2 = model2_model.model
model3 = model3_model.model

input_tensor = model1.input

# init coverage table
model_layer_dict1, model_layer_dict2, model_layer_dict3 = init_coverage_tables(model1, model2, model3)

# ==============================================================================================
# start gen inputs
i = 0
for _ in range(args.seeds):
    print(bcolors.OKBLUE + "seed %d" % i + bcolors.ENDC)
    i += 1
    gen_index = randint(0, len(raw_x) - 1)
    gen = raw_x[gen_index]

    gen_value = test_vec_x[gen_index]
    gen_value = np.expand_dims(gen_value, axis=0)
    orig = gen.copy()

    # first check if input already induces differences
    pred1, pred2, pred3 = model1.predict(gen_value), model2.predict(gen_value), model3.predict(gen_value)
    label1, label2, label3 = np.argmax(pred1[0]), np.argmax(pred2[0]), np.argmax(pred3[0])
    if not label1 == label2 == label3:
        print(bcolors.OKGREEN + 'input already causes different outputs: {}, {}, {}'.format(str(label1),
                                                                                            str(label2),
                                                                                            str(label3)) + bcolors.ENDC)

        update_coverage(gen_value, model1, model_layer_dict1, args)
        update_coverage(gen_value, model2, model_layer_dict2, args)
        update_coverage(gen_value, model3, model_layer_dict3, args)

        print(bcolors.OKGREEN + 'covered neurons percentage %d neurons %.3f, %d neurons %.3f, %d neurons %.3f'
              % (len(model_layer_dict1), neuron_covered(model_layer_dict1)[2], len(model_layer_dict2),
                 neuron_covered(model_layer_dict2, args)[2], len(model_layer_dict3),
                 neuron_covered(model_layer_dict3, args)[2]) + bcolors.ENDC)
        averaged_nc = (neuron_covered(model_layer_dict1, args)[0] + neuron_covered(model_layer_dict2, args)[0] +
                       neuron_covered(model_layer_dict3, args)[0]) / \
                        float(neuron_covered(model_layer_dict1, args)[1] +
                              neuron_covered(model_layer_dict2, args)[1] +
                              neuron_covered(model_layer_dict3, args)[1])
        print(bcolors.OKGREEN + 'averaged covered neurons %.3f' % averaged_nc + bcolors.ENDC)

        gen_deprocessed = data_deprocess(gen)

        # save the result to disk
        f = open('./generated_inputs/' + "already_differ_" + args.transformation + "_"
                 + args.coverage + "_" + args.test_generation + "_"
                 + str(label1) + "_" + str(label2)
                 + "_" + str(label3) + ".txt", 'w')
        f.write(gen_deprocessed)
        f.close()
        continue

    # if all label agrees
    orig_label = label1
    layer_name1, index1 = neuron_to_cover(model_layer_dict1)
    layer_name2, index2 = neuron_to_cover(model_layer_dict2)
    layer_name3, index3 = neuron_to_cover(model_layer_dict3)

    # construct joint loss function
    if args.target_model == 0:
        loss1 = -args.weight_diff * K.mean(model1.get_layer('predictions').output[..., orig_label])
        loss2 = K.mean(model2.get_layer('predictions').output[..., orig_label])
        loss3 = K.mean(model3.get_layer('predictions').output[..., orig_label])
    elif args.target_model == 1:
        loss1 = K.mean(model1.get_layer('predictions').output[..., orig_label])
        loss2 = -args.weight_diff * K.mean(model2.get_layer('predictions').output[..., orig_label])
        loss3 = K.mean(model3.get_layer('predictions').output[..., orig_label])
    elif args.target_model == 2:
        loss1 = K.mean(model1.get_layer('predictions').output[..., label1])
        loss2 = K.mean(model2.get_layer('predictions').output[..., orig_label])
        loss3 = -args.weight_diff * K.mean(model3.get_layer('predictions').output[..., orig_label])
    loss1_neuron = K.mean(model1.get_layer(layer_name1).output[..., index1])
    loss2_neuron = K.mean(model2.get_layer(layer_name2).output[..., index2])
    loss3_neuron = K.mean(model3.get_layer(layer_name3).output[..., index3])
    layer_output = (loss1 + loss2 + loss3) + args.weight_nc * (loss1_neuron + loss2_neuron + loss3_neuron)

    # for adversarial image generation
    final_loss = K.mean(layer_output)

    # we compute the gradient of the input picture wrt this loss
    grads = normalize(K.gradients(final_loss, input_tensor)[0])

    # this function returns the loss and grads given the input picture
    iterate = K.function([input_tensor], [grads])

    # we run gradient ascent for 20 steps
    for iters in range(args.grad_iterations):
        grads_value = iterate([gen_value])

        if args.transformation == 'synonym':
            gen, return_type = constarint_synonym(gen, grads_value, args)

        if not return_type: continue

        raw_x[gen_index] = gen
        temp_vec_x, test_vec_x = data_preprocess(raw_x)
        gen_value = test_vec_x[gen_index]
        gen_value = np.expand_dims(gen_value, axis=0)

        pred1, pred2, pred3 = model1.predict(gen_value), model2.predict(gen_value), model3.predict(gen_value)
        label1, label2, label3 = np.argmax(pred1[0]), np.argmax(pred2[0]), np.argmax(pred3[0])

        print("label1 :", label1, " label2 :", label2, " label3 :", label3)
        if not label1 == label2 == label3:

            update_coverage(gen_value, model1, model_layer_dict1, args)
            update_coverage(gen_value, model2, model_layer_dict2, args)
            update_coverage(gen_value, model3, model_layer_dict3, args)

            print(bcolors.OKGREEN + 'covered neurons percentage %d neurons %.3f, %d neurons %.3f, %d neurons %.3f'
                  % (len(model_layer_dict1), neuron_covered(model_layer_dict1, args)[2], len(model_layer_dict2),
                     neuron_covered(model_layer_dict2, args)[2], len(model_layer_dict3),
                     neuron_covered(model_layer_dict3, args)[2]) + bcolors.ENDC)
            averaged_nc = (neuron_covered(model_layer_dict1, args)[0] + neuron_covered(model_layer_dict2, args)[0] +
                            neuron_covered(model_layer_dict3, args)[0]) / \
                            float(neuron_covered(model_layer_dict1, args)[1] +
                                  neuron_covered(model_layer_dict2, args)[1] +
                                  neuron_covered(model_layer_dict3, args)[1])
            print(bcolors.OKGREEN + 'averaged covered neurons %.3f' % averaged_nc + bcolors.ENDC)

            gen_deprocessed = data_deprocess(gen)
            orig_deprocessed = data_deprocess(orig)
            #
            # # save the result to disk
            f = open('./generated_inputs/' + args.transformation + "_"
                     + args.coverage + "_" + args.test_generation + "_" + str(label1) + "_"
                     + str(label2) + "_" + str(label3) + ".txt", 'w')
            f.write(gen_deprocessed)
            f.close()
            break