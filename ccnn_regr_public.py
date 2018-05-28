# -*- coding: utf-8 -*-
"""
Created on Thu Nov 09 11:43:51 2017

This script trains the fully connected layers of a connectome-convolutional neural 
network on the public dataset to regress chronological age against resting-state 
functional connectivity matrices. Weights and biases of the fully connected 
layers are randomly initialized using Xavier initialization. The weights and
biases of the convolutional layers are constants corresponding to those learned
previously on the public dataset to classify age category. These values are stored 
in 'weights_public.pickle' in the root directory, which is generated by 
'ccnn_class_publictrain.py'.
The learned weights and biases of the fully connected layers are saved in
'weights_public_regr.pickle' which can then be used for adapting the network
to the in-house dataset. To this end, use the 'ccnn_regr_transfer.py' script.

This script was used for the transfer learning regression condition in the manuscript 
'Transfer learning improves resting-state functional connectivity pattern 
analysis using convolutional neural networks' by Vakli, Deák-Meszlényi, Hermann,
& Vidnyánszky.

This script is partially based on code from Deep learning course by Udacity: 
https://github.com/tensorflow/tensorflow/blob/master/tensorflow/examples/udacity/4_convolutions.ipynb

@author: Pál Vakli & Regina J. Deák-Meszlényi (RCNS-HAS-BIC)
"""
# %% ########################### Loading data #################################

# Importing necessary libraries
import numpy as np
import tensorflow as tf
from six.moves import cPickle as pickle

# Loading the connectivity matrices
picklefile = "CORR_tensor_public_regr.pickle"

with open(picklefile, 'rb') as f:
    save = pickle.load(f)
    data_tensor = save['data_tensor']
    del save

# Loading labels
labels_csv = np.loadtxt("labels_public_regr.csv", delimiter=',')
labels = labels_csv[:, 1]
labels = np.reshape(labels, (labels.shape[0], -1))

# Loading weights
picklefile = "weights_public.pickle"
        
with open(picklefile, 'rb') as f:
    save = pickle.load(f)
    layer1_weights_age = save['layer1_weights']
    layer1_biases_age = save['layer1_biases']
    layer2_weights_age = save['layer2_weights']
    layer2_biases_age = save['layer2_biases']
    layer3_weights_age = save['layer3_weights']
    layer3_biases_age = save['layer3_biases']
    layer4_weights_age = save['layer4_weights']
    layer4_biases_age = save['layer4_biases']
    del save    

# %% ####################### Function definitions #############################
# Define functions for cross-validation, tensor randomization and normalization 
# and performance calculation

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
def randomize_tensor(dataset, labels):                                         # sorrendcsere
    permutation = np.random.permutation(labels.shape[0])
    shuffled_dataset = dataset[permutation,:,:,:]
    shuffled_labels = labels[permutation,:]
    return shuffled_dataset, shuffled_labels

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
keep_pr = 0.6     # the probability that each element is kept during dropout

# Replacing NaNs with 0s and normalizing data
data_tensor[np.isnan(data_tensor)] = 0
data_tensor = normalize_tensor(data_tensor)

# Training data and labels
train_data = data_tensor.astype(np.float32)
train_labels = labels

# %% ##################### launching TensorFlow ###############################

# Drawing the computational graph    
graph = tf.Graph()
    
with graph.as_default():
    
    # Input data placeholders
    tf_train_dataset = tf.placeholder(tf.float32, shape=(batch_size, image_size, image_size, num_channels))
    tf_train_labels = tf.placeholder(tf.float32, shape=(batch_size, num_labels))
      
    # Network weight variables: Xavier initialization for better convergence in deep layers
    layer1_weights = tf.constant(layer1_weights_age, name="layer1_weights")
    layer1_biases = tf.constant(layer1_biases_age, name="layer1_biases")
    layer2_weights = tf.constant(layer2_weights_age, name="layer2_weights")
    layer2_biases = tf.constant(layer2_biases_age, name="layer2_biases")    
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

    # Calculate loss-function (cross-entropy) in training
    loss = tf.losses.mean_squared_error(labels=tf_train_labels, predictions=model(tf_train_dataset, keep_pr)) 
            
    # Optimizer definition
    learning_rate = 0.0005
    optimizer = tf.train.AdamOptimizer(learning_rate).minimize(loss) 
    
    # Calculate predictions from training data
    train_prediction = model(tf_train_dataset, keep_pr)
            
    # Number of iterations
    num_steps = 10001
      
# Start TensorFlow session
with tf.Session(graph=graph) as session:
    
    # Initializing variables    
    tf.global_variables_initializer().run()
    
    # Iterating over the training set       
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
            
        # At every 500. step give some feedback on the progress
        if (step % 500 == 0):
            print('Minibatch loss at step %d: %f' % (step, l))
            print('Minibatch R squared: %.2f' % r_squared(labels=batch_labels, predictions=predictions))
                    
    # Saving final weights and bias terms
    layer1_weights_final = layer1_weights.eval()
    layer1_biases_final = layer1_biases.eval()
    layer2_weights_final = layer2_weights.eval()
    layer2_biases_final = layer2_biases.eval()
    layer3_weights_final = layer3_weights.eval()
    layer3_biases_final = layer3_biases.eval()
    layer4_weights_final = layer4_weights.eval()
    layer4_biases_final = layer4_biases.eval()

# Saving weights
pickle_file = "weights_public_regr.pickle"
    
try:
    f = open(pickle_file, 'wb')
    save = {
            'layer1_weights': layer1_weights_final,
            'layer1_biases': layer1_biases_final,
            'layer2_weights': layer2_weights_final,
            'layer2_biases': layer2_biases_final,
            'layer3_weights': layer3_weights_final,
            'layer3_biases': layer3_biases_final,
            'layer4_weights': layer4_weights_final,
            'layer4_biases': layer4_biases_final,
            }
    pickle.dump(save, f, pickle.HIGHEST_PROTOCOL)
    f.close()
except Exception as e:
    print('Unable to save data to', pickle_file, ':', e)
    raise