from secml.ml.classifiers.pytorch.tests.test_c_classifier_pytorch import TestCClassifierPyTorch
from secml.testing import CUnitTest

try:
    import torch
    import torchvision
except ImportError:
    CUnitTest.importskip("torch")
    CUnitTest.importskip("torchvision")
else:
    from torch import nn, optim
    from torchvision import transforms

from secml.data.loader import CDLRandom
from secml.data.splitter import CTrainTestSplit
from secml.ml.classifiers import CClassifierPyTorch
from secml.ml.features import CNormalizerMinMax


class Net(nn.Module):
    """
    Model with input size (-1, 5) for blobs dataset
    with 5 features
    """

    def __init__(self, n_features, n_classes):
        """Example network."""
        super(Net, self).__init__()
        self.fc1 = nn.Linear(n_features, 10)
        self.fc2 = nn.Linear(10, n_classes)

    def forward(self, x):
        x = torch.relu(self.fc1(x))
        x = self.fc2(x)
        return x


class TestCClassifierPyTorchBlobs(TestCClassifierPyTorch):

    def setUp(self):
        self.logger.info("Testing Blobs Model")
        super(TestCClassifierPyTorchBlobs, self).setUp()
        self._dataset_creation_blobs()
        self._model_creation_blobs()
        self.clf.fit(self.tr)

    def _dataset_creation_blobs(self):
        # generate synthetic data
        self.ds = CDLRandom(n_samples=self.n_samples_tr + self.n_samples_ts,
                            n_classes=self.n_classes,
                            n_features=self.n_features, n_redundant=0,
                            n_clusters_per_class=1,
                            class_sep=1, random_state=0).load()

        # Split in training and test
        splitter = CTrainTestSplit(train_size=self.n_samples_tr,
                                   test_size=self.n_samples_ts,
                                   random_state=0)
        self.tr, self.ts = splitter.split(self.ds)

        # Normalize the data
        nmz = CNormalizerMinMax()
        self.tr.X = nmz.fit_transform(self.tr.X)
        self.ts.X = nmz.transform(self.ts.X)

    def _model_creation_blobs(self):
        torch.manual_seed(0)
        net = Net(n_features=self.n_features, n_classes=self.n_classes)
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.SGD(net.parameters(),
                              lr=0.1, momentum=0.9)
        optimizer_scheduler = torch.optim.lr_scheduler.MultiStepLR(optimizer, [5, 8], gamma=0.1)

        self.clf = CClassifierPyTorch(model=net,
                                      loss=criterion,
                                      optimizer=optimizer,
                                      optimizer_scheduler=optimizer_scheduler,
                                      epochs=10,
                                      batch_size=self.batch_size)

    def test_layer_names(self):
        self._test_layer_names()

    def test_layer_shapes(self):
        self._test_layer_shapes()

    def test_get_params(self):
        self._test_get_params()

    def test_set_params(self):
        self._test_set_params()

    def test_performance(self):
        self._test_performance()

    def test_predict(self):
        self._test_predict()

    def test_out_at_layer(self):
        self._test_out_at_layer(layer_name="fc1")

    def test_grad_x(self):
        self._test_grad_x(layer_names=["fc1", 'fc2', None])

    def test_softmax_outputs(self):
        self._test_softmax_outputs()

    def test_save_load(self):
        self._test_save_load(self._model_creation_blobs)
        # TODO: ISOLATE WHEN ABLE TO EXPAND THE UNITTESTS
        # Test for set_state and get_state
        pred_y = self.clf.predict(self.ts.X)
        self.logger.info(
            "Predictions before restoring state:\n{:}".format(pred_y))
        state = self.clf.get_state(return_optimizer=False)
        self.logger.info("State of classifier:\n{:}".format(state))

        # Create an entirely new clf without optimizer
        net2 = Net(n_features=self.n_features, n_classes=self.n_classes)

        clf2 = CClassifierPyTorch(model=net2,
                                  loss=None,
                                  optimizer=None,
                                  optimizer_scheduler=None,
                                  epochs=10,
                                  batch_size=self.batch_size)

        # Restore state
        clf2.set_state(state)

        pred_y_post = clf2.predict(self.ts.X)
        self.logger.info(
            "Predictions after restoring state:\n{:}".format(pred_y_post))

        self.assert_array_equal(pred_y, pred_y_post)
