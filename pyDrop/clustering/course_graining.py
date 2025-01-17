"""
=========================================================================================
                                Clustering Methods
=========================================================================================
CGCluster:
    coarse-grained clustering wrapper for any cluster method
    purpose: Increases the ability of unsupervised models to capture smaller clusters through 
        course-graining. Trains on the coarse-grained data and may therefore be less able
        to capture fine-detail decision boundaries
KMCalico:
    (Iterative clustering assisted by coarse-graining) developed in the following paper
    doi: 10.1021/acs.analchem.7b02688 
    Purpose: Iteratively course-grains the data and the updates the starting location 
        of the K-means clustering algorithm. This method is fast and still technically
        trains on the original data with new center starting locations. 
"""

from copy import deepcopy
import numpy as np
from sklearn.cluster import KMeans, OPTICS
from sklearn.metrics.cluster import rand_score, homogeneity_score, completeness_score

from pyDrop.exceptions import ModelValueError, AmbiguousCGFunction

class ModuloBins:
    """Coarse Grains data using the same behavior as the modulo operator.
    CG is performed using a modulo(mod) and remainder(rem) to calculate 
    the id that satisfies: bin# = mod*id + rem
    Parameters
    ----------
    mod : int, default=100
        the modulo that divides the input data
    rem : int, default=0
        the remainder that adds to the input data
    Usage
    -----
    >>> binf = ModuloBins()
    >>> data = np.array([1253,254,3098,490])
    >>> bins = binf.value_to_id(ids) 
    >>> bin_centers = binf.id_to_bin_center(bins) # coarse-grained data
    """
    def __init__(self, mod: int=100, rem: int=0):
        self.mod = mod
        self.rem = rem

        # Bin finding/evaluating functions to be called with np.arrays
        self.id_to_bin_start = np.vectorize(self._id_to_bin_start)
        self.id_to_bin_center = np.vectorize(self._id_to_bin_center)
        self.value_to_id = np.vectorize(self._value_to_id)

    def _id_to_bin_start(self, idx: int):
        return float(idx*self.mod + self.rem)
    
    def _id_to_bin_center(self, idx: int):
        return float(idx*self.mod + self.rem) + self.mod/2
    
    def _value_to_id(self, value: float):
        return int((value-self.rem)/self.mod)
    
class LinSpaceBins:
    """Coarse Grains data from bin created from a linear space of the data.
    CG is performed using bins linearly spaced from min to max with
    n_bins number of bins. 
    Parameters
    ----------
    min : float
        inclusive minimum value for the start of the bins. Any values less
        than min are assiged the bin id of 0
    max : float
        exclusive maximum value for the end of the bins. Any values greater
        than max are assigned the bin id of n_bins (maximum bin id)
    n_bins : int, default=100
        number of bins to subdivide the space into
    Usage
    -----
    >>> binf = LinSpaceBins(0,3000)
    >>> data = np.array([1253,254,3098,490])
    >>> bins = binf.value_to_id(ids) 
    >>> bin_centers = binf.id_to_bin_center(bins) # coarse-grained data
    """
    def __init__(self, min: float, max: float, n_bins: int=100):
        self.min = min
        self.max = max
        self.n_bins = n_bins

        self.step = float(max-min)/n_bins

        # Bin finding/evaluating functions to be called with np.arrays
        self.id_to_bin_start = np.vectorize(self._id_to_bin_start)
        self.id_to_bin_center = np.vectorize(self._id_to_bin_center)
        self.value_to_id = np.vectorize(self._value_to_id)
    
    def _id_to_bin_start(self, idx: int):
        if idx >= self.n_bins:
            return self.max - self.step # format goes from [min, max)
        elif idx < 0:
            return self.min
        else:
            return self.min + idx*self.step
    
    def _id_to_bin_center(self, idx: int):
        if idx >= self.n_bins:
            return self.max - (self.step/2)
        elif idx < 0:
            return self.min + (self.step/2)
        else:
            return self.min + idx*self.step + self.step/2
    
    def _value_to_id(self, value: float):
        if value <= self.min:
            return 0
        elif value > self.max:
            return self.n_bins
        else:
            return int((value - self.min) // self.step)
    
class ArrangeBins(LinSpaceBins):
    """Coarse Grains data from bin created from a linear space of the data.
    CG is performed using bins linearly spaced from min to max with a step
    size of step. Functionally, ArrangeBins is identical to LinSpaceBins with
    the only difference being how the linear space if defined. 
    Parameters
    ----------
    min : float
        inclusive minimum value for the start of the bins. Any values less
        than min are assiged the bin id of 0
    max : float
        exclusive maximum value for the end of the bins. Any values greater
        than max are assigned the bin id of n_bins (maximum bin id)
    step : float
        step between the start of adjacent bins
    Usage
    -----
    >>> binf = ArrangeBins(0,3000,100)
    >>> data = np.array([1253,254,3098,490])
    >>> bins = binf.value_to_id(ids) 
    >>> bin_centers = binf.id_to_bin_center(bins) # coarse-grained data
    """
    def __init__(self, min: float, max: float, step: float):
        self.min = min
        self.max = max
        self.step = step

        self.bins = np.arange(self.min, self.max, self.step)
        self.n_bins = len(self.bins)

        # Bin finding/evaluating functions to be called with np.arrays
        self.id_to_bin_start = np.vectorize(self._id_to_bin_start)
        self.id_to_bin_center = np.vectorize(self._id_to_bin_center)
        self.value_to_id = np.vectorize(self._value_to_id)

class Bins:
    """Creates and Stores multiple coarse-graining functions for ease of use
    Valid binning functions include LinSpaceBins, ArrangeBins, and ModuloBins and
    can be applied to various axes.
    Parameters
    ----------
    default_binf : ModuloBins | ArrangeBins | LinSpaceBins
        the default bin function to apply when no specified bin function is given
    Usage
    -----
    >>> bins = Bins()
    >>> binfs = [ModuloBins(100), ModuloBins(25)]
    >>> bins.add_axes(binfs)
    >>> ids = bins.value_to_id(data)
    >>> coarse_grained_data = bins.id_to_bin_center(ids)
    """
    def __init__(self, default_binf=ModuloBins):
        self.default_binf = default_binf
        self.bin_functions = []

    def add_axis(self, binf=None):
        """adds a single bin function.
        A valid bin function can include ModuloBins, LinSpaceBins, ArrangeBins, 
        or any coarse-graining object with vectorized value_to_id, id_to_bin_start,
        and id_to_bin_center methods to manipulate the data. 
        Parameters
        ----------
        binf : ModuloBins | ArrangeBins | LinSpaceBins, default=None
            binf function to apply to axis len(self.binf_functions)
        Returns
        -------
        None
        """
        if not binf:
            binf = self.default_binf()
        self.bin_functions.append(binf)

    def add_axes(self, binfs):
        """Addes multiple bin functions in series in the order recieved
        Acts identically to add_axis but for multiple inputs. 
        Parameters
        ----------
        x : str, default=True
            desc
        Parameters
        ----------
        binfs : list(ModuloBins | ArrangeBins | LinSpaceBins)
        Returns
        -------
        None
        """
        for binf in binfs:
            self.add_axis(binf)

    def get_num_axes(self):
        """returns the number of axes, which is the number of currently specified
        functions.
        Parameters
        ----------
        None

        Returns
        -------
        int
            current number of bin functions
        """
        return len(self.bin_functions)

    def get_binf(self, axis):
        """gets the bin function acting along axis <axis>
        Parameters
        ----------
        axis : int
        Returns
        -------
        ModuloBins | ArrangeBins | LinSpaceBins
            The bin function that acts along axis <axis>
        """
        return self.bin_functions[axis]
    
    #TODO: reduce the following functions a bit
    def id_to_bin_start(self, ids):
        """ converts a sequence of bin ids to bin start values
        returns an array of the same size as the input with bin start values
        that correspond to the ids given and the stored bin functions acting along
        each axis. 
        Parameters
        ----------
        ids : np.ndarray
            ids must be a numpy array where the length of axis 1 is the same
            as the number of bin function/axes currently stored.
        Returns
        -------
        np.ndarray
            array of bin start values where column i corresponds to the 
            start values of bins for ids[:,i] passed to the ith bin function
            in self.bin_functions
        """
        if len(ids.shape) == 1:
            ids = ids.reshape(-1, 1)
        n_samples, n_features = ids.shape
        assert n_features == len(self.bin_functions)
        values = np.zeros(ids.shape)
        for binf, axis_idx in zip(self.bin_functions, range(n_features)):
            values[:,axis_idx] = binf.id_to_bin_start(ids[:,axis_idx])
        return values
    
    def id_to_bin_center(self, ids):
        """ converts a sequence of bin ids to bin center values
        returns an array of the same size as the input with bin center values
        that correspond to the ids given and the stored bin functions acting along
        each axis. 
        Parameters
        ----------
        ids : np.ndarray
            ids must be a numpy array where the length of axis 1 is the same
            as the number of bin function/axes currently stored.
        Returns
        -------
        np.ndarray
            array of bin center values where column i corresponds to the 
            center values of bins for ids[:,i] passed to the ith bin function
            in self.bin_functions
        """
        if len(ids.shape) == 1:
            ids = ids.reshape(-1, 1)
        n_samples, n_features = ids.shape
        assert n_features == len(self.bin_functions)
        values = np.zeros(ids.shape)
        for binf, axis_idx in zip(self.bin_functions, range(n_features)):
            values[:,axis_idx] = binf.id_to_bin_center(ids[:,axis_idx])
        return values
    
    def value_to_id(self, values):
        """ converts a sequence of values to bin ids
        returns an array of the same size as the input with bin ids
        that correspond to the values given and the stored bin functions acting along
        each axis. 
        Parameters
        ----------
        values : np.ndarray
            values must be a numpy array where the length of axis 1 is the same
            as the number of bin function/axes currently stored.
        Returns
        -------
        np.ndarray
            array of bin ids where column i corresponds to the bin ids
            for values[:,i] passed to the ith bin function in self.bin_functions
        """
        if len(values.shape) == 1:
            values = values.reshape(-1, 1)
        n_samples, n_features = values.shape
        assert n_features == len(self.bin_functions)
        ids = np.zeros(values.shape)
        for binf, axis_idx in zip(self.bin_functions, range(n_features)):
            ids[:,axis_idx] = binf.value_to_id(values[:,axis_idx])
        return ids

class CGCluster:
    """ A coarse-graining wrapper for any cluster model
    Data is first coarse-grained using the Bins class and bin functions
    are added to accomodate the number of columns in the input data. The
    data is then coarse-grained and the given model is run. Can return the
    model and scores for the model with and without coarse-graining. 
    Parameters
    ----------
    bins : default=pydrop.clustering.Bins()
        can be any class that stores a number of bin functions
    model : default=sklearn.cluster.OPTICS()
        can be any clustering model with fit, predict, and fitpredict 
        methods. See sklearn.cluster documentation for a number of models
    Usage
    -----
    >>> model = CGCluster()
    >>> model.fit(data)
    >>> y_pred = model.predict(data, model="coarse")
    """
    def __init__(self, bins=Bins(), model=OPTICS()):
        self.bins = bins
        self.model = model

        self.coarse_model = deepcopy(model)

    def fit_uniform_coarse_grain(self, n_features, binf=ModuloBins(100)):
        """creates bin functions that matches the number of features of the 
        input data. All bin functions are the same and any previous bin functions
        are overriden
        Parameters
        ----------
        n_features : int
            number of features and number of required bin functions
        binf : default=ModuloBins(100)
            a bin function to uniformly apply to all features
        Returns
        -------
        None
        """
        bin_functions = [binf]*n_features
        self.bins.add_axes(bin_functions)

    def coarse_grain(self, X):
        """Coarse grains the data 
        returns the centers of the bins that correspond to the input
        data and the specified bin functions. If no bin functions are specified, the 
        default bin functions are applied uniformly to each axis. 
        Parameters
        ----------
        X : np.ndarray
            input data of shape (#features, #samples)
        Returns
        -------
        np.ndarray
            coarse-grained data of size (#features, < #samples). The 
            number of samples returned is always less than or equal to
            the number of sampels given. 
        """
        n_samples, n_features = X.shape
        n_defined_bins = self.bins.get_num_axes()
        if n_defined_bins == 0:
            print(f"no axes defined, using default ModuloBins bins for coarse-graining")
            self.fit_uniform_coarse_grain(n_features)
        elif n_defined_bins < n_features:
            raise AmbiguousCGFunction(f"ambiguous bins definition: {n_defined_bins} \
                                      axes defined for bins but there are {n_features} total axes.")
        
        x_grained_bins = self.bins.value_to_id(X)
        x_grained_bins = np.unique(x_grained_bins, axis=0)
        x_grained_centers = self.bins.id_to_bin_center(x_grained_bins)

        return x_grained_centers
    
    def fit(self, X):
        """fits the data
        first coarse-grains the data using the given bin functions and
        then fits the given clustering model on the coarse-grained data
        Parameters
        ----------
        X : np.ndarray
            input training data of shape (#features, #samples)
        Returns
        -------
        None
        """
        x_grained_centers = self.coarse_grain(X)
        self.coarse_model.fit(x_grained_centers)

    def predict(self, X, model="coarse"):
        """predicts the labels of the given data
        predictions can be made using the coarse-grained model or 
        the default model. 
        Parameters
        ----------
        X : np.ndarray
            input data of shape (#features, #samples)
        model : str, default="coarse"
            must be "coarse" or "default"
        Returns
        -------
        np.ndarray
            array of labels predicted from the given data
        """
        y_pred = None
        if model=="coarse":
            y_pred = self.coarse_model.predict(X)
        elif model=="default":
            y_pred = self.model.fit_predict(X)
        else:
            raise ModelValueError("model must be coarse or default")
        return y_pred
    
    def scores(self, X, y_true, model="coarse"):
        """returns a summary of the scores for the given model
        Parameters
        ----------
        X : np.ndarray
            input data of shape (#features, #samples)
        y_true: np.ndarray
            true labels values of the input data for supervised scores 
        model : str, default="coarse"
            must be "coarse" or "default"
        Returns
        -------
        dict where keys=["rand_score", "homogeneity_score", "completeness_score", "n_misclassified"]
            dictionary of scores returned on the given data
        """
        y_pred = self.predict(X, model=model)
        r_score = rand_score(y_true, y_pred)
        scores = {"rand_score": r_score,
                  "homogeneity_score": homogeneity_score(y_true, y_pred),
                  "completeness_score": completeness_score(y_true, y_pred),
                  "n_misclassified": len(y_true)*(1-r_score)
                 }
        return scores

class KMCalico(CGCluster):
    """ A coarse-graining wrapper for the KNN Calico method
    Data is first coarse-grained using the Bins class and bin functions
    are added to accomodate the number of columns in the input data. The
    data is then coarse-grained and cluster centers are obtained using KMeans.
    Finally, those centers are used as input to a final KMeans model acting on
    the original (not coarse-grained) data. 
    Parameters
    ----------
    bins : default=pydrop.clustering.Bins()
        can be any class that stores a number of bin functions
    k_means_model : default=sklearn.cluster.KMeans()
        can be any clustering Kmeans model with fit, predict, and
        fitpredict methods. Cluster centers must be obtainable with
        a model.cluster_centers_ variable. 
    Usage
    -----
    >>> model = KMCalico()
    >>> model.fit(data)
    >>> y_pred = model.predict(data, model="fine")
    """
    def __init__(self, bins=Bins(), k_means_model=KMeans()):
        """

        """
        # initialize data and the expected number of clusters 
        self.bins = bins
        self.model = k_means_model

        self.coarse_model = deepcopy(k_means_model)
        self.coarse_model.set_params(n_init='auto')

        self.fine_model = deepcopy(k_means_model)
        self.fine_model.set_params(n_init=1)

    def fit(self, X):
        """fits the data using the Calico algorithm
        first coarse-grains the data using the given bin functions and
        then fits the given coarse clustering model on the coarse-grained data. Then
        uses the centers as input to the fine clustering model that trains using the 
        original data. 
        Parameters
        ----------
        X : np.ndarray
            input training data of shape (#features, #samples)
        Returns
        -------
        None
        """
        x_grained_centers = self.coarse_grain(X)
        self.coarse_model.fit(x_grained_centers)
        coarse_centers = self.coarse_model.cluster_centers_

        self.fine_model.set_params(init=coarse_centers)
        self.fine_model.fit(X)

    def predict(self, X, model="fine", return_centers=False):
        """predicts the labels of the given data
        predictions can be made using the coarse-grained model, fine
        model, or the default model. 
        Parameters
        ----------
        X : np.ndarray
            input data of shape (#features, #samples)
        model : str, default="coarse"
            must be "coarse", "fine", or "default"
        Returns
        -------
        np.ndarray
            array of labels predicted from the given data
        """
        y_pred = None
        centers = None
        if model=="fine":
            y_pred = self.fine_model.predict(X)
            centers = self.fine_model.cluster_centers_
        elif model=="coarse":
            y_pred = self.coarse_model.predict(X)
            centers = self.coarse_model.cluster_centers_
        elif model=="default":
            y_pred = self.model.fit_predict(X)
            centers = self.model.cluster_centers_
        else:
            raise ModelValueError("model must be fine, coarse, or default")
        if return_centers:
            return y_pred, centers
        else:
            return y_pred

