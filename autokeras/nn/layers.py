from abc import abstractmethod

import torch
from torch import nn
from keras import layers
from torch.nn import functional

from autokeras.constant import Constant


class AvgPool(nn.Module):
    def __init__(self):
        super().__init__()

    @abstractmethod
    def forward(self, input_tensor):
        pass


class GlobalAvgPool1d(AvgPool):
    def forward(self, input_tensor):
        return functional.avg_pool1d(input_tensor, input_tensor.size()[2:]).view(input_tensor.size()[:2])


class GlobalAvgPool2d(AvgPool):
    def forward(self, input_tensor):
        return functional.avg_pool2d(input_tensor, input_tensor.size()[2:]).view(input_tensor.size()[:2])


class GlobalAvgPool3d(AvgPool):
    def forward(self, input_tensor):
        return functional.avg_pool3d(input_tensor, input_tensor.size()[2:]).view(input_tensor.size()[:2])


class StubLayer:
    def __init__(self, input_node=None, output_node=None):
        self.input = input_node
        self.output = output_node
        self.weights = None

    def build(self, shape):
        pass

    def set_weights(self, weights):
        self.weights = weights

    def import_weights(self, torch_layer):
        pass

    def import_weights_keras(self, keras_layer):
        pass

    def export_weights(self, torch_layer):
        pass

    def export_weights_keras(self, keras_layer):
        pass

    def get_weights(self):
        return self.weights

    def size(self):
        return 0

    @property
    def output_shape(self):
        return self.input.shape

    def to_real_layer(self):
        pass


class StubWeightBiasLayer(StubLayer):
    def import_weights(self, torch_layer):
        self.set_weights((torch_layer.weight.data.cpu().numpy(), torch_layer.bias.data.cpu().numpy()))

    def import_weights_keras(self, keras_layer):
        self.set_weights(keras_layer.get_weights())

    def export_weights(self, torch_layer):
        torch_layer.weight.data = torch.Tensor(self.weights[0])
        torch_layer.bias.data = torch.Tensor(self.weights[1])

    def export_weights_keras(self, keras_layer):
        keras_layer.set_weights(self.weights)


class StubBatchNormalization(StubWeightBiasLayer):
    def __init__(self, num_features, input_node=None, output_node=None):
        super().__init__(input_node, output_node)
        self.num_features = num_features

    def import_weights(self, torch_layer):
        self.set_weights((torch_layer.weight.data.cpu().numpy(),
                          torch_layer.bias.data.cpu().numpy(),
                          torch_layer.running_mean.cpu().numpy(),
                          torch_layer.running_var.cpu().numpy(),
                          ))

    def export_weights(self, torch_layer):
        torch_layer.weight.data = torch.Tensor(self.weights[0])
        torch_layer.bias.data = torch.Tensor(self.weights[1])
        torch_layer.running_mean = torch.Tensor(self.weights[2])
        torch_layer.running_var = torch.Tensor(self.weights[3])

    def size(self):
        return self.num_features * 4

    @abstractmethod
    def to_real_layer(self):
        pass


class StubBatchNormalization1d(StubBatchNormalization):
    def to_real_layer(self):
        return torch.nn.BatchNorm1d(self.num_features)


class StubBatchNormalization2d(StubBatchNormalization):
    def to_real_layer(self):
        return torch.nn.BatchNorm2d(self.num_features)


class StubBatchNormalization3d(StubBatchNormalization):
    def to_real_layer(self):
        return torch.nn.BatchNorm3d(self.num_features)


class StubDense(StubWeightBiasLayer):
    def __init__(self, input_units, units, input_node=None, output_node=None):
        super().__init__(input_node, output_node)
        self.input_units = input_units
        self.units = units

    @property
    def output_shape(self):
        return self.units,

    def import_weights_keras(self, keras_layer):
        self.set_weights((keras_layer.get_weights()[0].T, keras_layer.get_weights()[1]))

    def export_weights_keras(self, keras_layer):
        keras_layer.set_weights((self.weights[0].T, self.weights[1]))

    def size(self):
        return self.input_units * self.units + self.units

    def to_real_layer(self):
        return torch.nn.Linear(self.input_units, self.units)


class StubConv(StubWeightBiasLayer):
    def __init__(self, input_channel, filters, kernel_size, input_node=None, output_node=None, stride=1):
        super().__init__(input_node, output_node)
        self.input_channel = input_channel
        self.filters = filters
        self.kernel_size = kernel_size
        self.stride = stride

    @property
    def output_shape(self):
        ret = list(self.input.shape[:-1])
        for index, dim in enumerate(ret):
            ret[index] = int((dim - self.kernel_size) / self.stride) + 1
        ret = ret + [self.filters]
        return tuple(ret)

    def import_weights_keras(self, keras_layer):
        self.set_weights((keras_layer.get_weights()[0].T, keras_layer.get_weights()[1]))

    def export_weights_keras(self, keras_layer):
        keras_layer.set_weights((self.weights[0].T, self.weights[1]))

    def size(self):
        return self.filters * self.kernel_size * self.kernel_size + self.filters

    @abstractmethod
    def to_real_layer(self):
        pass


class StubConv1d(StubConv):
    def to_real_layer(self):
        return torch.nn.Conv1d(self.input_channel,
                               self.filters,
                               self.kernel_size,
                               stride=self.stride,
                               padding=int(self.kernel_size / 2))


class StubConv2d(StubConv):
    def to_real_layer(self):
        return torch.nn.Conv2d(self.input_channel,
                               self.filters,
                               self.kernel_size,
                               stride=self.stride,
                               padding=int(self.kernel_size / 2))


class StubConv3d(StubConv):
    def to_real_layer(self):
        return torch.nn.Conv3d(self.input_channel,
                               self.filters,
                               self.kernel_size,
                               stride=self.stride,
                               padding=int(self.kernel_size / 2))


class StubAggregateLayer(StubLayer):
    def __init__(self, input_nodes=None, output_node=None):
        if input_nodes is None:
            input_nodes = []
        super().__init__(input_nodes, output_node)


class StubConcatenate(StubAggregateLayer):
    @property
    def output_shape(self):
        ret = 0
        for current_input in self.input:
            ret += current_input.shape[-1]
        ret = self.input[0].shape[:-1] + (ret,)
        return ret

    def to_real_layer(self):
        return TorchConcatenate()


class StubAdd(StubAggregateLayer):
    @property
    def output_shape(self):
        return self.input[0].shape

    def to_real_layer(self):
        return TorchAdd()


class StubFlatten(StubLayer):
    @property
    def output_shape(self):
        ret = 1
        for dim in self.input.shape:
            ret *= dim
        return ret,

    def to_real_layer(self):
        return TorchFlatten()


class StubReLU(StubLayer):
    def to_real_layer(self):
        return torch.nn.ReLU()


class StubSoftmax(StubLayer):
    def to_real_layer(self):
        return torch.nn.LogSoftmax(dim=1)


class StubPooling(StubLayer):
    def __init__(self, kernel_size=2, input_node=None, output_node=None, stride=None, padding=0):
        super().__init__(input_node, output_node)
        self.kernel_size = kernel_size
        self.stride = stride or kernel_size
        self.padding = padding

    @property
    def output_shape(self):
        ret = tuple()
        for dim in self.input.shape[:-1]:
            ret = ret + (max(int(dim / self.kernel_size), 1),)
        ret = ret + (self.input.shape[-1],)
        return ret

    @abstractmethod
    def to_real_layer(self):
        pass


class StubPooling1d(StubPooling):
    def to_real_layer(self):
        return torch.nn.MaxPool1d(Constant.POOLING_KERNEL_SIZE)


class StubPooling2d(StubPooling):
    def to_real_layer(self):
        return torch.nn.MaxPool2d(Constant.POOLING_KERNEL_SIZE)


class StubPooling3d(StubPooling):
    def to_real_layer(self):
        return torch.nn.MaxPool3d(Constant.POOLING_KERNEL_SIZE)


class StubGlobalPooling(StubLayer):
    def __init__(self, input_node=None, output_node=None):
        super().__init__(input_node, output_node)

    @property
    def output_shape(self):
        return self.input.shape[-1],

    @abstractmethod
    def to_real_layer(self):
        pass


class StubGlobalPooling1d(StubGlobalPooling):
    def to_real_layer(self):
        return GlobalAvgPool1d()


class StubGlobalPooling2d(StubGlobalPooling):
    def to_real_layer(self):
        return GlobalAvgPool2d()


class StubGlobalPooling3d(StubGlobalPooling):
    def to_real_layer(self):
        return GlobalAvgPool3d()


class StubDropout(StubLayer):
    def __init__(self, rate, input_node=None, output_node=None):
        super().__init__(input_node, output_node)
        self.rate = rate

    @abstractmethod
    def to_real_layer(self):
        pass


class StubDropout1d(StubDropout):
    def to_real_layer(self):
        return torch.nn.Dropout(self.rate)


class StubDropout2d(StubDropout):
    def to_real_layer(self):
        return torch.nn.Dropout2d(self.rate)


class StubDropout3d(StubDropout):
    def to_real_layer(self):
        return torch.nn.Dropout3d(self.rate)


class StubInput(StubLayer):
    def __init__(self, input_node=None, output_node=None):
        super().__init__(input_node, output_node)


def is_layer(layer, layer_type):
    if layer_type == 'Input':
        return isinstance(layer, StubInput)
    if layer_type == 'Conv':
        return isinstance(layer, StubConv)
    if layer_type == 'Dense':
        return isinstance(layer, (StubDense,))
    if layer_type == 'BatchNormalization':
        return isinstance(layer, (StubBatchNormalization,))
    if layer_type == 'Concatenate':
        return isinstance(layer, (StubConcatenate,))
    if layer_type == 'Add':
        return isinstance(layer, (StubAdd,))
    if layer_type == 'Pooling':
        return isinstance(layer, StubPooling)
    if layer_type == 'Dropout':
        return isinstance(layer, (StubDropout,))
    if layer_type == 'Softmax':
        return isinstance(layer, (StubSoftmax,))
    if layer_type == 'ReLU':
        return isinstance(layer, (StubReLU,))
    if layer_type == 'Flatten':
        return isinstance(layer, (StubFlatten,))
    if layer_type == 'GlobalAveragePooling':
        return isinstance(layer, StubGlobalPooling)


def layer_width(layer):
    if is_layer(layer, 'Dense'):
        return layer.units
    if is_layer(layer, 'Conv'):
        return layer.filters
    raise TypeError('The layer should be either Dense or Conv layer.')


class TorchConcatenate(nn.Module):
    def forward(self, input_list):
        return torch.cat(input_list, dim=1)


class TorchAdd(nn.Module):
    def forward(self, input_list):
        return input_list[0] + input_list[1]


class TorchFlatten(nn.Module):
    def forward(self, input_tensor):
        return input_tensor.view(input_tensor.size(0), -1)


def keras_dropout(layer, rate):
    input_dim = len(layer.input.shape)
    if input_dim == 2:
        return layers.SpatialDropout1D(rate)
    elif input_dim == 3:
        return layers.SpatialDropout2D(rate)
    elif input_dim == 4:
        return layers.SpatialDropout3D(rate)
    else:
        return layers.Dropout(rate)


def to_real_keras_layer(layer):
    if is_layer(layer, 'Dense'):
        return layers.Dense(layer.units, input_shape=(layer.input_units,))
    if is_layer(layer, 'Conv'):
        return layers.Conv2D(layer.filters,
                             layer.kernel_size,
                             input_shape=layer.input.shape,
                             padding='same')  # padding
    if is_layer(layer, 'Pooling'):
        return layers.MaxPool2D(2)
    if is_layer(layer, 'BatchNormalization'):
        return layers.BatchNormalization(input_shape=layer.input.shape)
    if is_layer(layer, 'Concatenate'):
        return layers.Concatenate()
    if is_layer(layer, 'Add'):
        return layers.Add()
    if is_layer(layer, 'Dropout'):
        return keras_dropout(layer, layer.rate)
    if is_layer(layer, 'ReLU'):
        return layers.Activation('relu')
    if is_layer(layer, 'Softmax'):
        return layers.Activation('softmax')
    if is_layer(layer, 'Flatten'):
        return layers.Flatten()
    if is_layer(layer, 'GlobalAveragePooling'):
        return layers.GlobalAveragePooling2D()


def set_torch_weight_to_stub(torch_layer, stub_layer):
    stub_layer.import_weights(torch_layer)


def set_keras_weight_to_stub(keras_layer, stub_layer):
    stub_layer.import_weights_keras(keras_layer)


def set_stub_weight_to_torch(stub_layer, torch_layer):
    stub_layer.export_weights(torch_layer)


def set_stub_weight_to_keras(stub_layer, keras_layer):
    stub_layer.export_weights_keras(keras_layer)


def get_conv_class(n_dim):
    conv_class_list = [StubConv1d, StubConv2d, StubConv3d]
    return conv_class_list[n_dim - 1]


def get_dropout_class(n_dim):
    dropout_class_list = [StubDropout1d, StubDropout2d, StubDropout3d]
    return dropout_class_list[n_dim - 1]


def get_global_avg_pooling_class(n_dim):
    global_avg_pooling_class_list = [StubGlobalPooling1d, StubGlobalPooling2d, StubGlobalPooling3d]
    return global_avg_pooling_class_list[n_dim - 1]


def get_pooling_class(n_dim):
    pooling_class_list = [StubPooling1d, StubPooling2d, StubPooling3d]
    return pooling_class_list[n_dim - 1]


def get_batch_norm_class(n_dim):
    batch_norm_class_list = [StubBatchNormalization1d, StubBatchNormalization2d, StubBatchNormalization3d]
    return batch_norm_class_list[n_dim - 1]


def get_n_dim(layer):
    if isinstance(layer, (StubConv1d, StubDropout1d, StubGlobalPooling1d, StubPooling1d, StubBatchNormalization1d)):
        return 1
    if isinstance(layer, (StubConv2d, StubDropout2d, StubGlobalPooling2d, StubPooling2d, StubBatchNormalization2d)):
        return 2
    if isinstance(layer, (StubConv3d, StubDropout3d, StubGlobalPooling3d, StubPooling3d, StubBatchNormalization3d)):
        return 3
    return -1
