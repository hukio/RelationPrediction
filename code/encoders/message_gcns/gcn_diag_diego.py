import numpy as np
import tensorflow as tf

from encoders.message_gcns.message_gcn import MessageGcn


class DiagGcnDiego(MessageGcn):

    def parse_settings(self):
        self.embedding_width = int(self.settings['InternalEncoderDimension'])
        self.dropout_keep_probability = float(self.settings['DropoutKeepProbability'])

    def local_initialize_train(self):
        vertex_feature_dimension = self.entity_count if self.onehot_input else self.embedding_width
        type_matrix_shape = (self.relation_count, self.embedding_width)
        vertex_matrix_shape = (vertex_feature_dimension, self.embedding_width)

        glorot_var_combined = np.sqrt(3/(vertex_matrix_shape[0] + vertex_matrix_shape[1]))
        type_init_var = 1

        self_initial = np.random.normal(0, glorot_var_combined, size=vertex_matrix_shape).astype(np.float32)
        vertex_projection_sender_f_initial = np.random.normal(0, glorot_var_combined, size=vertex_matrix_shape).astype(np.float32)
        vertex_projection_sender_b_initial = np.random.normal(0, glorot_var_combined, size=vertex_matrix_shape).astype(
            np.float32)

        type_initial_forward = np.random.normal(0, type_init_var, size=type_matrix_shape).astype(np.float32)
        type_initial_backward = np.random.normal(0, type_init_var, size=type_matrix_shape).astype(np.float32)

        message_bias = np.zeros(self.embedding_width).astype(np.float32)

        self.V_proj_sender_forward = tf.Variable(vertex_projection_sender_f_initial)
        self.V_proj_sender_backward = tf.Variable(vertex_projection_sender_b_initial)

        self.V_self = tf.Variable(self_initial)

        self.V_types_forward = tf.Variable(type_initial_forward)
        self.V_types_backward = tf.Variable(type_initial_backward)

        self.B_message = tf.Variable(message_bias)


    def local_get_weights(self):
        return [self.V_proj_sender_forward, self.V_proj_sender_backward,
                self.V_types_forward, self.V_types_backward,
                self.V_self,
                self.B_message]

    def compute_messages(self, sender_features, receiver_features):
        sender_terms = self.dot_or_lookup(sender_features, self.V_proj_sender_forward)
        receiver_terms = self.dot_or_lookup(receiver_features, self.V_proj_sender_backward)

        message_types = self.get_graph().get_type_indices()
        forward_type_biases = tf.nn.embedding_lookup(self.V_types_forward, message_types)
        backward_type_biases = tf.nn.embedding_lookup(self.V_types_backward, message_types)

        forward_messages = sender_terms + forward_type_biases
        backward_messages = receiver_terms + backward_type_biases

        return forward_messages, backward_messages

    def compute_self_loop_messages(self, vertex_features):
        return self.dot_or_lookup(vertex_features, self.V_self)


    def combine_messages(self, forward_messages, backward_messages, self_loop_messages, previous_code, mode='train'):
        mtr_f = self.get_graph().forward_incidence_matrix(normalization=('global', 'recalculated'))
        mtr_b = self.get_graph().backward_incidence_matrix(normalization=('global', 'recalculated'))

        collected_messages_f = tf.sparse_tensor_dense_matmul(mtr_f, forward_messages)
        collected_messages_b = tf.sparse_tensor_dense_matmul(mtr_b, backward_messages)

        new_embedding = self_loop_messages + collected_messages_f + collected_messages_b + self.B_message

        if self.use_nonlinearity:
            new_embedding = tf.nn.relu(new_embedding)

        return new_embedding
