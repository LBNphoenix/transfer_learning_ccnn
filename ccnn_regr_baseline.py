# -*- coding: utf-8 -*-
"""
Created on Thu Oct 19 14:59:51 2017

This script trains a connectome-convolutional neural network on the in-house dataset to 
regress chronological age against resting-state functional connectivity matrices 
using 10-fold cross-validation (the folds are stored in 'folds_inhouse.npy'). 
The results are saved into 'results_ccnn_regr_baseline.npz'.

This script was used for the baseline regression condition in the manuscript 
'Transfer learning improves resting-state functional connectivity pattern 
analysis using convolutional neural networks' by Vakli, Deák-Meszlényi, Hermann,
& Vidnyánszky.

This script is partially based on code from Deep learning course by Udacity: 
https://github.com/tensorflow/tensorflow/blob/master/tensorflow/examples/udacity/4_convolutions.ipynb

@author: Pál Vakli & Regina J. Deák-Meszlényi (RCNS-HAS-BIC)
"""
# %% ########################## Loading data ##################################                
# Importing necessary libraries
import numpy as np
import tensorflow as tf
from six.moves import cPickle as pickle

# loading the correlation matrices
pickle_file = 'CORR_tensor_inhouse.pickle'
with open(pickle_file, 'rb') as f:
  save = pickle.load(f)
  data_tensor = save['data_tensor']
  del save                                                                     # hint to help gc free up memory

# Loading the labels
labels_csv = np.loadtxt("labels_inhouse.txt", delimiter=',')
labels = labels_csv[:, 2]
labels = np.reshape(labels, (labels.shape[0], -1))

subjects = labels_csv[:, 0]

# %% ####################### Function definitions #############################
# Define functions for cross-validation, tensor randomization and normalization 
# and performance calculation

# create_train_and_test_folds randomly divides subjectIDs stored in subjects to 
# num_folds sets
# INPUT: num_folds: number of folds in cross-validation (integer)
#        subjects: list of unique subject IDs
# OUTPUT: IDs: array storing unique subject IDs with num_folds columns: 
#              each column contains IDs of test subjects of the given fold
def create_train_and_test_folds(num_folds, subjects):                          
    n = np.ceil(len(subjects)/num_folds).astype(np.int)
    np.random.shuffle(subjects)
    if len(subjects) != n*num_folds:
        s = np.zeros(n*num_folds)
        s[:len(subjects)] = subjects
        subjects = s
    IDs = subjects.reshape((n, num_folds))
    return IDs

# normalize_tensor standardizes an n dimesional np.array to have zero mean and 
# standard deviation of 1
def normalize_tensor(data_tensor):
    data_tensor -= np.mean(data_tensor)
    data_tensor /= np.max(np.abs(data_tensor))
    return data_tensor

# randomize_tensor generates a random permutation of instances and the 
# corresponding labels before training
# INPUT: dataset: 4D tensor (np.array), instances are concatenated along the 
#                 first (0.) dimension
#        labels: 1D vector (np.array), storing labels of instances in dataset
# OUTPUT: shuffled_dataset: 4D tensor (np.array), instances are permuted along 
#                           the first (0.) dimension
#         shuffled_labels: 1D vector (np.array), storing labels of instances in 
#                           shuffled_dataset
def randomize_tensor(dataset, labels):
    permutation = np.random.permutation(labels.shape[0])
    shuffled_dataset = dataset[permutation,:,:,:]
    shuffled_labels = labels[permutation]
    return shuffled_dataset, shuffled_labels

# create_train_and_test_data creates and prepares training and test datasets and 
# labels for a given fold of cross-validation
# INPUT: fold: number of the given fold (starting from 0)
#        IDs: array storing unique subject IDs with num_folds columns: each 
#             column contains IDs of test subjects of the given fold 
#             (output of reate_train_and_test_folds)
#        subjects: list of subject IDs corresponding to the order of instances 
#                  stored in the dataset (ID of the same subject might appear 
#                  more than once)
#        labels: 1D vector (np.array) storing instance labels as integers
#        data_tensor: 4D tensor (np.array), instances are concatenated along the 
#                     first (0.) dimension
# OUTPUT: train_data: 4D tensor (np.array) of normalized and randomized train 
#                     instances of the given fold
#         train_labels: 1D vector (np.array), storing labels of instances in 
#                       train_data
#         test_data: 4D tensor (np.array) of normalized (but not randomized) 
#                    test instances of the given fold
#         test_labels: 1D vector (np.array), storing labels of instances in 
#                      test_data
def create_train_and_test_data(fold, IDs, subjects, labels, data_tensor):
    testIDs = np.in1d(subjects, IDs[:,fold])
        
    test_data = normalize_tensor(data_tensor[testIDs,:,:,:]).astype(np.float32)
    test_labels = labels[testIDs]
    
    train_data = normalize_tensor(data_tensor[~testIDs,:,:,:]).astype(np.float32)
    train_labels = labels[~testIDs]
    train_data, train_labels = randomize_tensor(train_data, train_labels)
    
    return train_data, train_labels, test_data, test_labels

# r_squared computes the cofficient of determination (R^2) for the predicted 
# chronological age values
# INPUT: labels: 1D vector (np.array) storing actual labels
#        predictions: 1D vector (np.array) storing predicted labels
# OUTPUT: rsq: R^2
def r_squared(labels, predictions):
    
    ss_res = np.mean(np.square(labels-predictions))
    ss_tot = np.mean(np.square(labels-np.mean(labels)))
    rsq = 1-(ss_res/ss_tot)
    
    return rsq

# %% ####### Preparing the data and initializing network parameters ###########

numROI = 111
num_channels = 1
num_labels = 1
image_size = numROI
batch_size = 4
patch_size = image_size
keep_pr = 0.6    # the probability that each element is kept during dropout
num_folds = 10

# Replacing NaNs with 0s and normalizing data
data_tensor[np.isnan(data_tensor)] = 0
data_tensor = normalize_tensor(data_tensor)

# Loading folds
IDs = np.load('folds_inhouse.npy')

# Variables to store test labels and predictions later on
test_labs = []
test_preds = []

# %% ###################### launching TensorFlow ##############################

# Iterating over folds
for i in range(num_folds):
    
    # Creating train and test data for the given fold
    train_data, train_labels, test_data, test_labels = create_train_and_test_data(i, IDs, subjects, labels, data_tensor)
    
    train_data = train_data[:, :image_size, :image_size, :]
    test_data = test_data[:, :image_size, :image_size, :]
    
    # Drawing the computational graph
    graph = tf.Graph()
    
    with graph.as_default():
    
        # Input data placeholders
        tf_train_dataset = tf.placeholder(tf.float32, shape=(batch_size, image_size, image_size, num_channels))
        tf_train_labels = tf.placeholder(tf.float32, shape=(batch_size, num_labels))
      
        # Test data is a constant
        tf_test_dataset = tf.constant(test_data)
      
        # Network weight variables: Xavier initialization for better convergence in deep layers
        layer1_weights = tf.get_variable("layer1_weights", shape=[1, patch_size, num_channels, 64],
                                         initializer=tf.contrib.layers.xavier_initializer())
        layer1_biases = tf.Variable(tf.constant(0.001, shape=[64]))
        layer2_weights = tf.get_variable("layer2_weights", shape=[patch_size, 1, 64, 256],
                                         initializer=tf.contrib.layers.xavier_initializer())
        layer2_biases = tf.Variable(tf.constant(0.001, shape=[256]))
        layer3_weights = tf.get_variable("layer3_weights", shape=[256, 96],
                                         initializer=tf.contrib.layers.xavier_initializer())
        layer3_biases = tf.Variable(tf.constant(0.01, shape=[96]))
        layer4_weights = tf.get_variable("layer4_weights", shape=[96, num_labels],
                                         initializer=tf.contrib.layers.xavier_initializer())
        layer4_biases = tf.Variable(tf.constant(0.01, shape=[num_labels]))
      
        # Convolutional network architecture
        def model(data, keep_pr):
            # First layer: line-by-line convolution with ReLU and dropout
            conv = tf.nn.conv2d(data, layer1_weights, [1, 1, 1, 1], padding='VALID')
            hidden = tf.nn.dropout(tf.nn.relu(conv+layer1_biases), keep_pr)
            # Second layer: convolution by column with ReLU and dropout
            conv = tf.nn.conv2d(hidden, layer2_weights, [1, 1, 1, 1], padding='VALID')
            hidden = tf.nn.dropout(tf.nn.relu(conv+layer2_biases), keep_pr)
            # Third layer: fully connected hidden layer with dropout and ReLU
            shape = hidden.get_shape().as_list()
            reshape = tf.reshape(hidden, [shape[0], shape[1] * shape[2] * shape[3]])
            hidden = tf.nn.dropout(tf.nn.relu(tf.matmul(reshape, layer3_weights) + layer3_biases), keep_pr)
            # Fourth (output) layer: fully connected layer with logits as output
            return tf.matmul(hidden, layer4_weights) + layer4_biases
      
        # Calculate loss-function (mean squared error)
        loss = tf.losses.mean_squared_error(labels=tf_train_labels, 
                                            predictions=model(tf_train_dataset, keep_pr))
            
        # Optimizer definition
        learning_rate = 0.0005
        optimizer = tf.train.AdamOptimizer(learning_rate).minimize(loss)
          
         # Calculate predictions from training data
        train_prediction = model(tf_train_dataset, keep_pr)
            
        # Number of iterations
        num_steps = 15001
      
        # Calculate predictions from test data (keep_pr of dropout is 1!)
        test_prediction = model(tf_test_dataset, 1)

    # Start TensorFlow session
    with tf.Session(graph=graph) as session:
        
        # Initializing variables
        tf.global_variables_initializer().run()
        print('Initialized')
        
        # Iterating over the test set
        for step in range(num_steps):
              
            offset = (step * batch_size) % (train_labels.shape[0] - batch_size)
            
            # If we have seen all training data at least once, re-randomize the order 
            # of instances
            if (offset == 0 ):
                train_data, train_labels = randomize_tensor(train_data, train_labels)
            
            # Create batch    
            batch_data = train_data[offset:(offset + batch_size), :, :, :]
            batch_labels = train_labels[offset:(offset + batch_size), :]
            
            # Feed batch data to the placeholders
            feed_dict = {tf_train_dataset : batch_data, tf_train_labels : batch_labels}
            _, l, predictions = session.run(
                    [optimizer, loss, train_prediction], feed_dict=feed_dict)
                
            # At every 400. step give some feedback on the progress
            if (step % 400 == 0):
                print('Minibatch loss at step %d: %f' % (step, l))
                print('Minibatch R squared: %.2f' % r_squared(labels=batch_labels, predictions=predictions))

        # Evaluate the trained model on the test data in the given fold
        test_pred = test_prediction.eval()                                       
        print('Test R squared: %.2f' % r_squared(labels=test_labels, predictions=test_pred))
        
        # Save test predictions and labels of this fold to a list
        test_labs.append(test_labels)
        test_preds.append(test_pred)

# Create np.array to store all predictions and labels
l = test_labs[0]
p = test_preds[0]   
# Iterate through the cross-validation folds    
for i in range(1, num_folds):
    l = np.vstack((l, test_labs[i]))
    p = np.vstack((p, test_preds[i]))

# Calculate final R^2    
print('Final R squared: %.2f' % r_squared(labels=l, predictions=p))

# Save data
np.savez("results_ccnn_regr_baseline.npz", labels=l, predictions=p, splits=IDs)