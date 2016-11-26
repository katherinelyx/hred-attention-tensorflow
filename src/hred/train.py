""" File to build and train the entire computation graph in tensorflow
"""

import numpy as np

from hred import HRED
import tensorflow as tf
from optimizer import Optimizer
import read_data

TRAIN_FILE = '../../data/tr_session.out'
VALIDATION_FILE = '../../data/val_session.out'
TEST_FILE = '../../data/test_session.out'
SMALL_FILE = '../../data/small_test_session.out'
eos = '2'

TRAIN_TFR = '../../data/tfrecords/train.tfrecords'
VALIDATION_TFR = '../../data/tfrecords/valid.tfrecords'
TEST_TFR = '../../data/tfrecords/test.tfrecords'
SMALL_TFR = '../../data/tfrecords/small.tfrecords'

if __name__ == '__main__':
    with tf.Graph().as_default():

        hred = HRED()
        batch_size = None
        max_length = None

        X = tf.placeholder(tf.int32, shape=(max_length, batch_size))
        Y = tf.placeholder(tf.int32, shape=(max_length, batch_size))
        HQ0 = tf.placeholder(tf.float32, (2, batch_size, hred.query_hidden_size))
        HS0 = tf.placeholder(tf.float32, (2, batch_size, hred.session_hidden_size))
        HD0 = tf.placeholder(tf.float32, (batch_size, hred.decoder_hidden_size))
        O0 = tf.placeholder(tf.float32, (batch_size, hred.output_hidden_size))
        L0 = tf.placeholder(tf.float32, (batch_size, hred.vocab_size))

        logits = hred.step(X, HQ0, HS0, HD0, O0, L0)
        # softmax = hred.softmax(logits)
        loss = hred.loss(logits, Y)
        optimizer = Optimizer(loss, initial_learning_rate=1e-2, num_steps_per_decay=15000,
                              decay_rate=0.1, max_global_norm=1.0)
        optimze = optimizer.optimize_op

        with tf.Session() as sess:

            sess.run(tf.initialize_all_variables())
            summary_writer = tf.train.SummaryWriter('logs/graph', sess.graph)

            label, input = read_data.read_and_decode(TEST_TFR)

            batch_size = 10
            max_length = 5

            for x in range(100):

                input_batch, labels_batch = tf.train.shuffle_batch(
                    [input, label], batch_size=batch_size,
                    capacity=2000,
                    min_after_dequeue=1000)

                inp_b = tf.cast(input_batch, tf.int32)
                lab_b = tf.cast(labels_batch, tf.int32)

                r = np.random.randint(0, hred.vocab_size, (max_length + 1, batch_size))
                x = r[:-1,:]
                y = r[1:,:]
                hq0 = np.zeros((2, batch_size, hred.query_hidden_size))
                hs0 = np.zeros((2, batch_size, hred.session_hidden_size))
                hd0 = np.zeros((batch_size, hred.decoder_hidden_size))
                o0 = np.zeros((batch_size, hred.output_hidden_size))
                l0 = np.zeros((batch_size, hred.vocab_size))

                # print(r)
                # print(x)
                # print(y)

                loss_out, _ = sess.run(
                    [loss, optimze],
                    {X: x, Y:y, HQ0: hq0, HS0: hs0, HD0: hd0, O0: o0, L0: l0}
                )

                print("Loss: %f" % loss_out)
