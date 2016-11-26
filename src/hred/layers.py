import tensorflow as tf
import numpy as np

import utils


def embedding_layer(x, name='embedding-layer', vocab_dim=90004, embedding_dim=256):
    """
    Used before the query encoder, to go from the vocabulary to an embedding
    """

    with tf.variable_scope(name):
        W = tf.get_variable(name="weights", shape=(vocab_dim, embedding_dim),
                            initializer=tf.random_normal_initializer(stddev=0.001))
        embedding = tf.nn.embedding_lookup(W, x)

    return embedding


def gru_layer_with_reset(h_prev, x_packed, name='gru', x_dim=256, y_dim=512):
    """
    Used for the query encoder layer. The encoder is reset after an EoQ symbol
    has been reached.

    :param h_prev: previous state of the GRU layer
    :param x_packed: x_packed should be a 2-tuple: (embedding, reset vector = x-mask)
    :return: updated hidden layer and reset hidden layer
    """

    # Unpack mandatory packed force_reset_vector, x = embedding
    x, reset_vector = x_packed

    with tf.variable_scope(name):
        h = _gru_layer(h_prev, x, 'gru', x_dim, y_dim)

        # Force reset hidden state: is set to zero if reset vector consists of zeros
        h_reset = reset_vector * h

    return tf.pack([h, h_reset])


def gru_layer_with_retain(h_prev, x_packed, name='gru', x_dim=256, y_dim=512):
    """
    Used for the session encoder layer. The current state of the session encoder
    should be retained if no EoQ symbol has been reached yet.
    :param h_prev: previous state of the GRU layer
    :param x_packed: x_packed should be a 2-tuple (embedding, retain vector = x-mask)
    """

    # Unpack mandatory packed retain_vector
    x, retain_vector = x_packed

    with tf.variable_scope(name):
        h = _gru_layer(h_prev, x, 'gru', x_dim, y_dim)

        # Force reset hidden state: is h_prev is retain vector consists of ones,
        # is h if retain vector consists of zeros
        h_retain = retain_vector * h_prev + (1 - retain_vector) * h

    return tf.pack([h, h_retain])


def gru_layer_with_state_reset(h_prev, x_packed, name='gru', x_dim=256, h_dim=512, y_dim=1024):
    """
    Used for the decoder layer
    :param h_prev: previous decoder state
    :param x_packed: should be a 3-tuple (embedder, mask, session_encoder)
    """

    # Unpack mandatory packed retain_vector and the state
    # x = embedder, ratain_vector = mask, state = session_encoder
    x, retain_vector, state = x_packed

    with tf.variable_scope(name):

        with tf.variable_scope('state_start'):
            W = tf.get_variable(name='weight', shape=(h_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
            b = tf.get_variable(name='bias', shape=(y_dim,), initializer=tf.constant_initializer(0.0))

            h_prev_state = retain_vector * h_prev + (1 - retain_vector) * tf.tanh(tf.matmul(state, W) + b)

        h = _gru_layer_with_state(h_prev_state, x, state, 'gru', x_dim, y_dim, h_dim)

    return h


def output_layer(x_packed, name='output', x_dim=256, y_dim=512, h_dim=512, s_dim=512):
    """
    Used after the decoder
    """

    h, x, state, = x_packed

    with tf.variable_scope(name):
        Wh = tf.get_variable(name='weight_hidden', shape=(h_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
        Ws = tf.get_variable(name='weight_state', shape=(s_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
        Wi = tf.get_variable(name='weight_input', shape=(x_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
        b = tf.get_variable(name='bias_input', shape=(y_dim,), initializer=tf.random_normal_initializer(stddev=0.001))

        y = tf.matmul(h, Wh) \
            + tf.matmul(state, Ws) \
            + tf.matmul(x, Wi) \
            + b

    return y


def logits_layer(x, name='logits', x_dim=512, y_dim=90004):
    """
    Used to compute the logits after the output layer.
    The logits could be fed to a softmax layer

    :param x: output (obtained in layers.output_layer)
    :return: logits
    """

    with tf.variable_scope(name):

        W = tf.get_variable(name='weight', shape=(x_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
        b = tf.get_variable(name='bias', shape=(y_dim,), initializer=tf.random_normal_initializer(stddev=0.001))

        y = tf.matmul(x, W) + b

    return y


def _gru_layer(h_prev, x, name='gru', x_dim=256, y_dim=512):
    """
    Used for both encoder layers
    """

    with tf.variable_scope(name):

        # Reset gate
        with tf.variable_scope('reset_gate'):
            Wi_r = tf.get_variable(name='weight_input', shape=(x_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
            Wh_r = tf.get_variable(name='weight_hidden', shape=(y_dim, y_dim), initializer=utils.orthogonal_initializer())
            b_r = tf.get_variable(name='bias', shape=(y_dim,), initializer=tf.constant_initializer(0.0))
            r = tf.sigmoid(tf.matmul(x, Wi_r)) + tf.matmul(h_prev, Wh_r) + b_r

        # Update gate
        with tf.variable_scope('update_gate'):
            Wi_z = tf.get_variable(name='weight_input', shape=(x_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
            Wh_z = tf.get_variable(name='weight_hidden', shape=(y_dim, y_dim), initializer=utils.orthogonal_initializer())
            b_z = tf.get_variable(name='bias', shape=(y_dim,), initializer=tf.constant_initializer(0.0))
            z = tf.sigmoid(tf.matmul(x, Wi_z)) + tf.matmul(h_prev, Wh_z) + b_z

        # Candidate update
        with tf.variable_scope('candidate_update'):
            Wi_h_tilde = tf.get_variable(name='weight_input', shape=(x_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
            Wh_h_tilde = tf.get_variable(name='weight_hidden', shape=(y_dim, y_dim), initializer=utils.orthogonal_initializer())
            b_h_tilde = tf.get_variable(name='bias', shape=(y_dim,), initializer=tf.constant_initializer(0.0))
            h_tilde = tf.tanh(tf.matmul(x, Wi_h_tilde)) + tf.matmul(r * h_prev, Wh_h_tilde) + b_h_tilde

        # Final update
        h = (np.float32(1.0) - z) * h_prev + z * h_tilde

    return h


def _gru_layer_with_state(h_prev, x, state, name='gru', x_dim=256, y_dim=1024, h_dim=512):
    """
    Used for decoder. In this GRU the state of the session encoder layer is used when
    computing the decoder updates.
    """

    with tf.variable_scope(name):

        # Reset gate
        with tf.variable_scope('reset_gate'):
            Wi_r = tf.get_variable(name='weight_input', shape=(x_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
            Wh_r = tf.get_variable(name='weight_hidden', shape=(y_dim, y_dim), initializer=utils.orthogonal_initializer())
            Ws_r = tf.get_variable(name='weight_state', shape=(h_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
            b_r = tf.get_variable(name='bias', shape=(y_dim,), initializer=tf.constant_initializer(0.0))
            r = tf.sigmoid(tf.matmul(x, Wi_r)) + tf.matmul(h_prev, Wh_r) + tf.matmul(state, Ws_r) + b_r

        # Update gate
        with tf.variable_scope('update_gate'):
            Wi_z = tf.get_variable(name='weight_input', shape=(x_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
            Wh_z = tf.get_variable(name='weight_hidden', shape=(y_dim, y_dim), initializer=utils.orthogonal_initializer())
            Ws_r = tf.get_variable(name='weight_state', shape=(h_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
            b_z = tf.get_variable(name='bias', shape=(y_dim,), initializer=tf.constant_initializer(0.0))
            z = tf.sigmoid(tf.matmul(x, Wi_z)) + tf.matmul(h_prev, Wh_z) + tf.matmul(state, Ws_r) + b_z

        # Candidate update
        with tf.variable_scope('candidate_update'):
            Wi_h_tilde = tf.get_variable(name='weight_input', shape=(x_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
            Wh_h_tilde = tf.get_variable(name='weight_hidden', shape=(y_dim, y_dim), initializer=utils.orthogonal_initializer())
            Ws_h_tilde = tf.get_variable(name='weight_state', shape=(h_dim, y_dim), initializer=tf.random_normal_initializer(stddev=0.001))
            b_h_tilde = tf.get_variable(name='bias', shape=(y_dim,), initializer=tf.constant_initializer(0.0))
            h_tilde = tf.tanh(tf.matmul(x, Wi_h_tilde)) + \
                      tf.matmul(r * h_prev, Wh_h_tilde) + \
                      tf.matmul(state, Ws_h_tilde) + \
                      b_h_tilde

        # Final update
        h = (np.float32(1.0) - z) * h_prev + z * h_tilde

    return h
