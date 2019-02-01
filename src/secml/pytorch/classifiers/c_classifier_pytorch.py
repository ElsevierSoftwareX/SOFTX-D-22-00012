"""
.. module:: CClassifierPyTorch
   :synopsis: Classifier with PyTorch Neural Network

.. moduleauthor:: Marco Melis <marco.melis@diee.unica.it>
.. moduleauthor:: Ambra Demontis <marco.melis@diee.unica.it>

"""
from copy import deepcopy

import torch
from torch.utils.data import DataLoader
import torch.optim as optim
from torch.autograd import Variable
import torchvision.transforms as transforms

from secml.array import CArray
from secml.data import CDataset
from secml.ml.classifiers import CClassifier
from secml.ml.classifiers.loss import CSoftmax
from secml.utils import load_dict, fm
from secml.utils.mixed_utils import AverageMeter

from secml.pytorch.settings import SECML_PYTORCH_USE_CUDA
from secml.pytorch.data import CDatasetPyTorch
from secml.pytorch.metrics import CMetricPyTorchAccuracy
from secml.pytorch.utils.optim_utils import add_weight_decay

# Use CUDA ?!
use_cuda = torch.cuda.is_available() and SECML_PYTORCH_USE_CUDA


# FIXME: inner preprocess not manage yet for training phase
class CClassifierPyTorch(CClassifier):
    """PyTorch Neural Network classifier.

    Parameters
    ----------
    model
        PyTorch Neural Network model or function which returns a model.
    learning_rate : float, optional
        Learning rate. Default 1e-2.
    momentum : float, optional
        Momentum factor. Default 0.9.
    weight_decay : float, optional
        Weight decay (L2 penalty). Control parameters regularization.
        Default 1e-4.
    loss : str, optional
        Identifier of the loss function to use for training.
        Default Cross-Entropy loss (cross-entropy).
    epochs : int, optional
        Maximum number of epochs of the training process. Default 100.
    gamma : float, optional
        Multiplicative factor of learning rate decay. Default: 0.1.
    lr_schedule : list, optional
        List of epoch indices. Must be increasing.
        The current learning rate will be multiplied by gamma
        once the number of epochs reaches each index.
    batch_size : int, optional
        Size of the batch for grouping samples. Default 1.
    regularize_bias : bool, optional
        If False, L2 regularization will NOT be applied to biases.
        Default True, so regularization will be applied to all parameters.
        If weight_decay is 0, regularization will not be applied anyway.
        If fit.warm_start is True, this parameter has no effect.
    train_transform : torchvision.transform or None, optional
        Transformation to be applied before training.
    preprocess : CNormalizer or None, optional
        Preprocessing for data. If not None and model state will be loaded
        using `.load_state()`, this should be an already-trained preprocessor
        or `.preprocess.fit(x)` should be called after `.load_state(x)`
        with appropriate input.
    input_shape : tuple, optional
        Shape of the input expected by the first layer of the network.
        If None, samples will not be reshaped before passing them to the net.
        If not set, `load_state` will not be available.
    softmax_outputs : bool, optional
        If True, apply softmax function to the outputs. Default False.
    random_state : int or None, optional
        If int, random_state is the seed used by the random number generator.
        If None, no fixed seed will be set.
    model_params : str or kwargs
        Any other keyword argument for the model function.
        If a string, must be a path to a dictionary where
         model parameters are stored.

    """
    __super__ = 'CClassifierPyTorch'

    def __init__(self, model, learning_rate=1e-2, momentum=0.9,
                 weight_decay=1e-4, loss='cross-entropy', epochs=100,
                 gamma=0.1, lr_schedule=(50, 75), batch_size=1,
                 regularize_bias=True, train_transform=None, preprocess=None,
                 input_shape=None, softmax_outputs=False,
                 random_state=None, **model_params):

        # Model and params
        self._model_base = model

        # If a string was passed as `model_params` try to load params from file
        if 'model_params' in model_params:
            model_params_url = model_params['model_params']
            if not fm.file_exist(model_params_url):
                raise ValueError(
                    "no file available at {:}".format(model_params_url))
            model_params = load_dict(model_params_url, int)

        self._model_params = model_params

        # Optimizer params (set the protected attrs to avoid
        # reinitialize the optimizer each time)
        self._learning_rate = float(learning_rate)
        self._momentum = float(momentum)
        self._weight_decay = float(weight_decay)

        # Training params
        self.loss_id = loss
        self.epochs = epochs
        self.gamma = gamma
        self.lr_schedule = lr_schedule
        self.batch_size = batch_size
        self.regularize_bias = regularize_bias
        self.train_transform = train_transform

        # Other parameters
        self.input_shape = input_shape
        self.softmax_outputs = softmax_outputs

        # Training vars
        self._start_epoch = 0
        self._acc = 0  # epoch accuracy FIXME: ON TRAINING SET
        self._best_acc = 0  # best accuracy FIXME: ON TRAINING SET

        self._random_state = random_state

        # PyTorch NeuralNetwork model
        self._model = None
        # PyTorch Optimizer
        self._optimizer = None

        # Initialize the model
        self.init_model()
        # Initialize the optimizer
        self.init_optimizer()

        if use_cuda is True:
            self.logger.info("Using CUDA for PyTorch computations!")

        super(CClassifierPyTorch, self).__init__(preprocess=preprocess)

    @property
    def model_params(self):
        """Model parameters dictionary."""
        return self._model_params

    @property
    def learning_rate(self):
        """Learning rate. """
        return self._learning_rate

    @learning_rate.setter
    def learning_rate(self, value):
        """Learning rate."""
        self._learning_rate = float(value)
        # We need to recreate the optimizer after param change
        self.init_optimizer()

    @property
    def momentum(self):
        """Momentum factor."""
        return self._momentum

    @momentum.setter
    def momentum(self, value):
        """Momentum factor."""
        self._momentum = float(value)
        # We need to recreate the optimizer after param change
        self.init_optimizer()

    @property
    def weight_decay(self):
        """Weight decay (L2 penalty). Control parameters regularization."""
        return self._weight_decay

    @weight_decay.setter
    def weight_decay(self, value):
        """Weight decay (L2 penalty). Control parameters regularization."""
        self._weight_decay = float(value)
        # We need to recreate the optimizer after param change
        self.init_optimizer()

    @property
    def loss_id(self):
        """Loss function for training (id)."""
        return self._loss_id

    @loss_id.setter
    def loss_id(self, value):
        """Loss function for training (id)."""
        self._loss_id = str(value)

    @property
    def epochs(self):
        """Maximum number of epochs of the training process."""
        return self._epochs

    @epochs.setter
    def epochs(self, value):
        """Maximum number of epochs of the training process."""
        self._epochs = int(value)

    @property
    def gamma(self):
        """Multiplicative factor of learning rate decay."""
        return self._gamma

    @gamma.setter
    def gamma(self, value):
        """Multiplicative factor of learning rate decay."""
        self._gamma = float(value)

    @property
    def lr_schedule(self):
        """List of epoch indices."""
        return self._lr_schedule

    @lr_schedule.setter
    def lr_schedule(self, value):
        """List of epoch indices."""
        self._lr_schedule = list(value)

    @property
    def batch_size(self):
        """Size of the batch for grouping samples."""
        return self._batch_size

    @batch_size.setter
    def batch_size(self, value):
        """Size of the batch for grouping samples."""
        self._batch_size = int(value)

    @property
    def regularize_bias(self):
        """If False, L2 regularization will NOT be applied to biases."""
        return self._regularize_bias

    @regularize_bias.setter
    def regularize_bias(self, value):
        """If False, L2 regularization will NOT be applied to biases."""
        self._regularize_bias = bool(value)

    @property
    def input_shape(self):
        """Shape of the model input."""
        return self._input_shape

    @input_shape.setter
    def input_shape(self, value):
        """Shape of the model input."""
        self._input_shape = value

    @property
    def softmax_outputs(self):
        """If True, outputs will be softmax-scaled."""
        return self._softmax_outputs

    @softmax_outputs.setter
    def softmax_outputs(self, value):
        """If True, outputs will be softmax-scaled."""
        self._softmax_outputs = value

    @property
    def start_epoch(self):
        """Current training epoch."""
        return self._start_epoch

    @property
    def acc(self):
        """Classification accuracy for current epoch."""
        # FIXME: ON TRAINING SET
        return self._acc

    @property
    def best_acc(self):
        """Best classification accuracy."""
        # FIXME: ON TRAINING SET
        return self._best_acc

    @property
    def w(self):
        """Concatenation of weights from each layer of the network."""
        w = CArray([])
        with torch.no_grad():
            for m in self._model.modules():
                if hasattr(m, 'weight') and m.weight is not None:
                    w = w.append(CArray(m.weight.data.cpu().numpy().ravel()))
        return w

    @property
    def b(self):
        """Concatenation of bias from each layer of the network."""
        b = CArray([])
        with torch.no_grad():
            for m in self._model.modules():
                if hasattr(m, 'bias') and m.bias is not None:
                    b = b.append(CArray(m.bias.data.cpu().numpy().ravel()))
        return b

    def __deepcopy__(self, memo, *args, **kwargs):
        """Called when copy.deepcopy(object) is called.

        `memo` is a memory dictionary needed by `copy.deepcopy`.

        """
        # Store and deepcopy the state of the optimizer/model
        state_dict = deepcopy(self.state_dict())

        # Remove optimizer and model before deepcopy (will be restored)
        optimizer = self._optimizer
        model = self._model
        self._optimizer = None
        self._model = None

        # Now we are ready to clone the clf
        new_obj = super(
            CClassifierPyTorch, self).__deepcopy__(memo, *args, **kwargs)

        # Restore optimizer/model in the current object
        self._optimizer = optimizer
        self._model = model

        # Set optimizer/model state in new object
        new_obj.init_model()
        new_obj.init_optimizer()
        new_obj.load_state(state_dict)

        # Restoring original CClassifier parameters
        # that may had been updated by `load_state`
        # Ugly, but required for managing the train/pretrain cases
        new_obj._classes = self.classes
        new_obj._n_features = self.n_features

        # Decrementing the start_epoch counter as the temporary
        # save/load of the state has incremented it
        new_obj._start_epoch -= 1

        return new_obj

    def init_model(self):
        """Initialize the PyTorch Neural Network model."""
        # Setting random seed
        if self._random_state is not None:
            torch.manual_seed(self._random_state)
            if use_cuda:
                torch.cuda.manual_seed_all(self._random_state)
                torch.backends.cudnn.deterministic = True

        # Call the specific model initialization method passing params
        self._model = self._model_base(**self._model_params)

        # Make sure that model is a proper PyTorch module
        if not isinstance(self._model, torch.nn.Module):
            raise TypeError("`model` must be a `torch.nn.Module`.")

        # Ensure we are using cuda if available
        if use_cuda is True:
            self._model = self._model.cuda()

    def init_optimizer(self):
        """Initialize the PyTorch Neural Network optimizer."""
        # Altering parameters by adding weight_decay only to proper params
        if self.weight_decay != 0 and self.regularize_bias is False:
            params = add_weight_decay(self._model, self.weight_decay)
        else:  # .. but only if necessary!
            params = self._model.parameters()

        # weight_decay is passed anyway to the optimizer and act as a default
        self._optimizer = optim.SGD(params,
                                    lr=self.learning_rate,
                                    momentum=self.momentum,
                                    weight_decay=self.weight_decay)

    def loss(self, x, target):
        """Return the loss function computed on input.

        Parameters
        ----------
        x : torch.Tensor
            Scores as 2D Tensor of shape (N, C).
        target : torch.Tensor
            Targets as 2D Tensor of shape (N, C).

        Returns
        -------
        loss : torch.Tensor
            Value of the loss. Single scalar tensor.

        """
        # As scores might have shape [N, 1, C], squeeze them
        x = x.squeeze(1)

        if self.loss_id == 'cross-entropy':
            # Cross-Entropy Loss (includes softmax)
            # target are one-hot encoded so we extract single targets
            return torch.nn.CrossEntropyLoss()(x, torch.max(target, 1)[1])
        elif self.loss_id == 'mse':
            # Mean Squared Error (MSE)
            return torch.nn.MSELoss(size_average=False)(x, target.float())
        else:
            raise ValueError("loss `{:}` not supported".format(self.loss_id))

    def _to_tensor(self, x):
        """Convert input array to tensor."""
        x = x.tondarray()
        x = torch.from_numpy(x)
        x = x.type(torch.FloatTensor)
        if use_cuda is True:
            x = x.cuda()
        return x

    def _get_test_input_loader(self, x, n_jobs=1):
        """Return a loader for input test data."""
        # Convert to CDatasetPyTorch and use a dataloader that returns batches
        dl = DataLoader(CDatasetPyTorch(x),
                        batch_size=self.batch_size,
                        shuffle=False,
                        num_workers=n_jobs-1)

        # Add a transformation that reshape samples to (C x H x W)
        dl.dataset.transform = transforms.Lambda(
            lambda p: p.reshape(self.input_shape))

        return dl

    def load_state(self, state_dict, dataparallel=False):
        """Load PyTorch objects state from dictionary.

        Parameters
        ----------
        state_dict : dict
            Dictionary with the state of the model, optimizer and last epoch.
            Should contain the following keys:
                - 'state_dict' state of the model as by model.state_dict()
                - 'optimizer' state of the optimizer as by optimizer.state_dict()
                - 'epoch' last epoch of the training process
        dataparallel : bool, optional
            If True, input state should be considered saved from a
            DataParallel model. Default False.

        """
        # Set this to True if optimizer needs to be recreated
        recreate_optimizer = False
        # Change optimizer-related parameters accordingly to state
        # The default (initial) parameters are stored
        # Parameters in `param_groups` list could be different
        # depending on the epoch the state has been stored
        # and will be restored later
        if 'defaults' in state_dict['optimizer']:
            defaults = state_dict['optimizer']['defaults']
            # set the protected attrs to avoid reinitialize
            # the optimizer each time
            self._learning_rate = float(defaults['lr'])
            self._momentum = float(defaults['momentum'])
            self._weight_decay = float(defaults['weight_decay'])
            recreate_optimizer = True
        else:
            # If the state dict does not contain the default values,
            # display warning and continue
            self.logger.warning("State dictionary has no defaults for the "
                                "optimizer parameters. Keeping current values")

        try:  # biases have been regularized?
            self.regularize_bias = bool(
                state_dict['optimizer']['regularize_bias'])
            recreate_optimizer = True
        except KeyError:
            pass  # `regularize_bias` not defined probably, use default

        if recreate_optimizer is True:
            self.init_optimizer()

        # Restore the state of the param_groups in the optimizer
        self._optimizer.load_state_dict(state_dict['optimizer'])

        # Restore the count of epochs
        self._start_epoch = state_dict['epoch']

        # Restore accuracy data if available
        self._acc = state_dict.get('acc', 0)
        self._best_acc = state_dict.get('best_acc', 0)

        # Restore the state of the model
        if dataparallel is True:
            # Convert a DataParallel model state to a normal model state
            # Get the keys to alter the dict on-the-fly
            keys = state_dict['state_dict'].keys()
            for k in keys:
                name = k.replace('module.', '')  # remove module.
                state_dict['state_dict'][name] = state_dict['state_dict'][k]
                state_dict['state_dict'].pop(k)
        self._model.load_state_dict(state_dict['state_dict'])

        # If input_shape is not set, try to load from state_dict
        if self.input_shape is None:
            self.input_shape = state_dict.get('input_shape', None)
        # Now input_shape should be not None, otherwise raise error
        if self.input_shape is None:
            raise RuntimeError("`input_shape` is not known. Cannot load state")

        # Restoring CClassifier params
        self._n_features = sum(self.input_shape)
        # For _classes we input a fake sample to the model and check output
        x = torch.rand(2, *self.input_shape).type(torch.FloatTensor)
        if use_cuda is True:
            x = x.cuda()
        self._classes = CArray.arange(self._model(x).shape[-1])

    def state_dict(self):
        """Return a dictionary with PyTorch objects state.

        Returns
        -------
        dict
            Dictionary with the state of the model, optimizer and last epoch.
            Will contain the following keys:
                - 'state_dict' state of the model as by model.state_dict()
                - 'optimizer' state of the optimizer as by optimizer.state_dict()
                - 'epoch' last epoch of the training process

        """
        state_dict = dict()
        state_dict['optimizer'] = self._optimizer.state_dict()
        # Saving other optimizer default parameters
        state_dict['optimizer']['defaults'] = self._optimizer.defaults
        state_dict['optimizer']['regularize_bias'] = self.regularize_bias
        state_dict['state_dict'] = self._model.state_dict()
        state_dict['epoch'] = self.start_epoch + 1
        state_dict['acc'] = self.acc
        state_dict['best_acc'] = self.best_acc
        state_dict['input_shape'] = self.input_shape
        return state_dict

    def fit(self, dataset, warm_start=False, store_best_params=True, n_jobs=1):
        """Trains the classifier.

        If specified, train_transform is applied to data.

        Parameters
        ----------
        dataset : CDataset
            Training set. Must be a :class:`.CDataset` instance with
            patterns data and corresponding labels.
        warm_start : bool, optional
            If False (default) model will be reinitialized before training.
            Otherwise the state of the model will be preserved.
        store_best_params : bool, optional
            If True (default) the best parameters by classification accuracy
             found during the training process are stored.
            Otherwise, the parameters from the last epoch are stored.
        n_jobs : int, optional
            Number of parallel workers to use for training the classifier.
            Default 1. Cannot be higher than processor's number of cores.

        Returns
        -------
        trained_cls : CClassifier
            Instance of the classifier trained using input dataset.

        Warnings
        --------
        preprocess is not applied to data before training. This behaviour
         will change in the feature.

        """
        if not isinstance(dataset, CDataset):
            raise TypeError(
                "training set should be provided as a CDataset object.")

        if self.preprocess is not None:
            # TODO: CHANGE THIS BEHAVIOUR
            self.logger.warning(
                "preprocess is not applied to training data. "
                "Use `train_transform` parameter if necessary.")

        if warm_start is False:
            # Resetting the classifier
            self.clear()
            # Storing dataset classes
            self._classes = dataset.classes
            self._n_features = dataset.num_features
            # Reinitialize the model as we are starting clean
            self.init_model()
            # Reinitialize count of epochs
            self._start_epoch = 0
            # Reinitialize accuracy and best accuracy
            self._best_acc = 0
            self._acc = 0
            # Reinitialize the optimizer as we are starting clean
            self.init_optimizer()

        return self._fit(dataset, store_best_params, n_jobs=n_jobs)

    def _fit(self, dataset, store_best_params=True, n_jobs=1):
        """Trains the classifier.

        If specified, train_transform is applied to data.

        Parameters
        ----------
        dataset : CDataset
            Training set. Must be a :class:`.CDataset` instance with
            patterns data and corresponding labels.
        store_best_params : bool, optional
            If True (default) the best parameters by classification accuracy
             found during the training process are stored.
            Otherwise, the parameters from the last epoch are stored.
        n_jobs : int, optional
            Number of parallel workers to use for training the classifier.
            Default 1. Cannot be higher than processor's number of cores.

        Returns
        -------
        trained_cls : CClassifier
            Instance of the classifier trained using input dataset.

        Warnings
        --------
        preprocess is not applied to data before training. This behaviour
         will change in the future.

        """
        if self.start_epoch >= self.epochs:
            self.logger.warning("Maximum number of epochs reached, "
                                "no training will be performed.")
            return self

        # Binarize labels using a OVA scheme
        ova_labels = dataset.get_labels_asbinary()

        # Convert to CDatasetPyTorch and use a dataloader that returns batches
        ds_loader = DataLoader(CDatasetPyTorch(dataset.X, ova_labels,
                                               transform=self.train_transform),
                               batch_size=self.batch_size,
                               shuffle=True,
                               num_workers=n_jobs-1)

        # Switch to training mode
        self._model.train()

        # Scheduler to adjust the learning rate depending on epoch
        scheduler = optim.lr_scheduler.MultiStepLR(
            self._optimizer, self.lr_schedule, gamma=self.gamma,
            last_epoch=self.start_epoch - 1)

        # Storing a copy of the best epoch
        # will be used as the final training state dict
        best_epoch = self.start_epoch
        best_state_dict = deepcopy(self.state_dict())

        for self._start_epoch in xrange(self.start_epoch, self.epochs):

            scheduler.step()  # Adjust the learning rate
            losses = AverageMeter()  # Logger of the loss value
            acc = AverageMeter()  # Logger of the accuracy

            # Log progress of epoch
            self.logger.info(
                'Epoch: [{curr_epoch}|{epochs}] LR: {lr} - STARTED'.format(
                    curr_epoch=self.start_epoch + 1,
                    epochs=self.epochs,
                    lr=scheduler.get_lr()[0],
                ))

            for batch_idx, (x, y) in enumerate(ds_loader):

                if use_cuda is True:
                    x, y = x.cuda(), y.cuda(async=True)
                x, y = Variable(x, requires_grad=True), Variable(y)

                # As y have shape [N, 1, C], squeeze them
                y = y.squeeze(1)

                # Compute output and loss
                logits = self._model(x)
                loss = self.loss(logits, y)

                # compute gradient and do SGD step
                self._optimizer.zero_grad()  # same as self._model.zero_grad()
                loss.backward()
                self._optimizer.step()

                losses.update(loss.item(), x.size(0))
                acc.update(CMetricPyTorchAccuracy().performance_score(
                    y_true=y.data, score=logits.data)[0].item(), x.size(0))

                # Log progress of batch
                self.logger.debug('Epoch: {epoch}, Batch: ({batch}/{size}) '
                                  'Loss: {loss:.4f} Acc: {acc:.2f}'.format(
                                    epoch=self.start_epoch + 1,
                                    batch=batch_idx + 1,
                                    size=len(ds_loader),
                                    loss=losses.avg,
                                    acc=acc.avg,
                                  ))

            # Log progress of epoch
            self.logger.info('Epoch: [{curr_epoch}|{epochs}] '
                             'Loss: {loss:.4f} Acc: {acc:.2f}'.format(
                               curr_epoch=self.start_epoch + 1,
                               epochs=self.epochs,
                               loss=losses.avg,
                               acc=acc.avg,
                             ))

            # Average accuracy after epoch FIXME: ON TRAINING SET
            self._acc = acc.avg

            # If the best parameters should be stored, store the current epoch
            # as best one only if accuracy is higher or at least same
            # (as the loss should be better anyway for latest epoch)
            if store_best_params is True and self.acc < self.best_acc:
                continue  # Otherwise do not store the current epoch
            else:  # Better accuracy or we should store the latest epoch anyway
                self._best_acc = self.acc
                best_epoch = self.start_epoch
                best_state_dict = deepcopy(self.state_dict())

        if store_best_params is True:
            self.logger.info(
                "Best accuracy {:} obtained on epoch {:}".format(
                    self.best_acc, best_epoch + 1))

        # Restoring the final state to use
        # (could be the best by accuracy score or the latest)
        self.load_state(best_state_dict)

        return self

    def decision_function(self, x, y, n_jobs=1):
        """Computes the decision function for each pattern in x.

        If a preprocess has been specified, input is normalized
        before computing the decision function.

        Parameters
        ----------
        x : CArray
            Array with new patterns to classify, 2-Dimensional of shape
            (n_patterns, n_features).
        y : int
            The label of the class wrt the function should be calculated.
        n_jobs : int, optional
            Number of parallel workers to use. Default 1.
            Cannot be higher than processor's number of cores.

        Returns
        -------
        score : CArray
            Value of the decision function for each test pattern.
            Dense flat array of shape (n_patterns,).

        """
        x = x.atleast_2d()  # Ensuring input is 2-D

        # Preprocessing data if a preprocess is defined
        if self.preprocess is not None:
            x = self.preprocess.normalize(x)

        return self._decision_function(x, y, n_jobs=n_jobs)

    def _decision_function(self, x, y, n_jobs=1):
        """Computes the decision function for each pattern in x.

        Parameters
        ----------
        x : CArray
            Array with new patterns to classify, 2-Dimensional of shape
            (n_patterns, n_features).
        y : int
            The label of the class wrt the function should be calculated.
        n_jobs : int, optional
            Number of parallel workers to use. Default 1.
            Cannot be higher than processor's number of cores.

        Returns
        -------
        score : CArray
            Value of the decision function for each test pattern.
            Dense flat array of shape (n_patterns,).

        """
        if self.is_clear():
            raise ValueError("make sure the classifier is trained first.")

        x = x.atleast_2d()  # Ensuring input is 2-D

        x_loader = self._get_test_input_loader(x, n_jobs=n_jobs)

        # Switch to evaluation mode
        self._model.eval()

        scores = None
        for batch_idx, (s, _) in enumerate(x_loader):

            # Log progress
            self.logger.info(
                'Classification: {batch}/{size}'.format(
                    batch=batch_idx,
                    size=len(x_loader)
                ))

            if use_cuda is True:
                s = s.cuda()
            s = Variable(s, requires_grad=True)

            with torch.no_grad():
                logits = self._model(s)
                logits = logits.squeeze(1)
                logits = CArray(logits.data.cpu().numpy()).astype(float)

            # Apply softmax-scaling if needed
            if self.softmax_outputs is True:
                logits = CSoftmax().softmax(logits)

            logits = logits[:, y]  # Extract desired class

            if scores is not None:
                scores = scores.append(logits, axis=0)
            else:
                scores = logits

        return scores.ravel()

    def predict(self, x, return_decision_function=False, n_jobs=1):
        """Perform classification of each pattern in x.

        If a preprocess has been specified,
         input is normalized before classification.

        Parameters
        ----------
        x : CArray
            Array with new patterns to classify, 2-Dimensional of shape
            (n_patterns, n_features).
        return_decision_function : bool, optional
            Whether to return the decision_function value along
            with predictions. Default False.
        n_jobs : int, optional
            Number of parallel workers to use for classification.
            Default 1. Cannot be higher than processor's number of cores.

        Returns
        -------
        labels : CArray
            Flat dense array of shape (n_patterns,) with the label assigned
             to each test pattern. The classification label is the label of
             the class associated with the highest score.
        scores : CArray, optional
            Array of shape (n_patterns, n_classes) with classification
             score of each test pattern with respect to each training class.
            Will be returned only if `return_decision_function` is True.

        """
        if self.is_clear():
            raise ValueError("make sure the classifier is trained first.")

        x_carray = CArray(x).atleast_2d()

        # Preprocessing data if a preprocess is defined
        if self.preprocess is not None:
            x_carray = self.preprocess.normalize(x_carray)

        x_loader = self._get_test_input_loader(x_carray, n_jobs=n_jobs)

        # Switch to evaluation mode
        self._model.eval()

        scores = None
        for batch_idx, (s, _) in enumerate(x_loader):

            # Log progress
            self.logger.info(
                'Classification: {batch}/{size}'.format(
                    batch=batch_idx,
                    size=len(x_loader)
                ))

            if use_cuda is True:
                s = s.cuda()
            s = Variable(s, requires_grad=True)

            with torch.no_grad():
                logits = self._model(s)
                logits = logits.squeeze(1)
                logits = CArray(logits.data.cpu().numpy()).astype(float)

            if scores is not None:
                scores = scores.append(logits, axis=0)
            else:
                scores = logits

        # Apply softmax-scaling if needed
        if self.softmax_outputs is True:
            scores = CSoftmax().softmax(scores)

        # The classification label is the label of the class
        # associated with the highest score
        labels = scores.argmax(axis=1).ravel()

        return (labels, scores) if return_decision_function is True else labels

    def _gradient_f(self, x, y=None, w=None, layer=None):
        """Computes the gradient of the classifier's decision function
         wrt decision function input.

        Parameters
        ----------
        x : CArray
            The gradient is computed in the neighborhood of x.
        y : int or None, optional
            Index of the class wrt the gradient must be computed.
            This is not required if:
             - `w` is passed and the last layer is used but
              softmax_outputs is False
             - an intermediate layer is used
        w : CArray or None, optional
            If CArray, will be passed to backward and must have a proper shape
            depending on the chosen output layer (the last one if `layer`
            is None). This is required if `layer` is not None.
        layer : str or None, optional
            Name of the layer.
            If None, the gradient at the last layer will be returned
             and `y` is required if `w` is None or softmax_outputs is True.
            If not None, `w` of proper shape is required.

        Returns
        -------
        gradient : CArray
            Gradient of the classifier's df wrt its input. Vector-like array.

        """
        if x.is_vector_like is False:
            raise ValueError("gradient can be computed on one sample only.")

        dl = self._get_test_input_loader(x)

        s = dl.dataset[0][0]  # Get the single and only point from the dl

        if use_cuda is True:
            s = s.cuda()
        s = s.unsqueeze(0)   # unsqueeze to simulate a single point batch
        s = Variable(s, requires_grad=True)

        # Get the model output at specific layer
        out = self._get_layer_output(s, layer=layer)

        # unsqueeze if net output does not take into account the batch size
        if len(out.shape) < len(s.shape):
            out = out.unsqueeze(0)

        if w is None:
            if layer is not None:
                raise ValueError(
                    "grad can be implicitly created only for the last layer. "
                    "`w` is needed when `layer` is not None.")
            if y is None:  # if layer is None -> y is required
                raise ValueError("The class label wrt compute the gradient "
                                 "at the last layer is required.")

            w_in = torch.FloatTensor(1, out.shape[-1])
            if use_cuda is True:
                w_in = w_in.cuda()
            w_in.zero_()
            w_in[0, y] = 1  # create a mask to get the gradient wrt y

        else:
            w_in = self._to_tensor(w.atleast_2d())

        w_in = w_in.unsqueeze(0)  # unsqueeze to simulate a single point batch

        # Apply softmax-scaling if needed
        if layer is None and self.softmax_outputs is True:
            out_carray = CArray(
                out.squeeze(0).data.cpu().numpy()).astype(float)
            softmax_grad = CSoftmax().gradient(out_carray, pos_label=y)
            w_in *= self._to_tensor(softmax_grad.atleast_2d()).unsqueeze(0)
        elif w is not None and y is not None:
            # Inform the user y has not been used
            self.logger.warning("`y` will be ignored!")

        out.backward(w_in)  # Backward on `out` (grad will appear on `s`)

        return CArray(s.grad.data.cpu().numpy().ravel())

    def _get_layer_output(self, s, layer=None):
        """Returns the output of the desired net layer.

        Parameters
        ----------
        s : torch.Tensor
            Input tensor to forward propagate.
        layer : str or None, optional
            Name of the layer.
            If None, the output of the last layer will be returned.

        Returns
        -------
        torch.Tensor
            Output of the desired layer.

        """
        # Switch to evaluation mode
        self._model.eval()

        if layer is None:  # Directly use the last layer
            s = self._model(s)  # Forward pass

        else:  # FIXME: THIS DOES NOT WORK IF THE FORWARD METHOD
                # HAS ANY SPECIAL OPERATION INSIDE (LIKE DENSENET)
            # Manual iterate the network and stop at desired layer
            # Use _model to iterate over first level modules only
            for m_k, m in self._model._modules.iteritems():
                s = m(s)  # Forward input trough module
                if m_k == layer:
                    # We found the desired layer
                    break
            else:
                if layer is not None:
                    raise ValueError(
                        "No layer `{:}` found!".format(layer))

        return s

    def get_layer_output(self, x, layer=None):
        """Returns the output of the desired net layer.

        Parameters
        ----------
        x : CArray
            Input data.
        layer : str or None, optional
            Name of the layer.
            If None, the output of the last layer will be returned.

        Returns
        -------
        CArray
            Output of the desired layer.

        """
        x_loader = self._get_test_input_loader(x)

        out = None
        for batch_idx, (s, _) in enumerate(x_loader):

            if use_cuda is True:
                s = s.cuda()
            s = Variable(s, requires_grad=True)

            with torch.no_grad():
                # Get the model output at specific layer
                s = self._get_layer_output(s, layer=layer)

            # Convert to CArray
            s = s.view(s.size(0), -1)
            s = CArray(s.data.cpu().numpy()).astype(float)

            if out is not None:
                out = out.append(s, axis=0)
            else:
                out = s

        return out
