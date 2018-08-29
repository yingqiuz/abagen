# -*- coding: utf-8 -*-

import itertools

from nilearn._utils import check_niimg_3d
import numpy as np
import pandas as pd
from scipy.ndimage.measurements import center_of_mass
from scipy.spatial.distance import cdist
from scipy.stats import zscore

AGG_FUNCS = dict(
    mean=np.mean,
    median=np.median
)


def check_atlas_info(atlas, info):
    """
    Checks whether provided `info` on `atlas` is sufficient for processing

    Parameters
    ----------
    atlas : niimg-like object
        Parcel image, where each parcel should be identified with a unique
        integer ID
    info : str or pandas.DataFrame, optional
        Filepath to or pre-loaded dataframe containing information about
        `atlas`. Must jhave _at least_ columns 'id', 'hemisphere', and
        'structure' containing information mapping atlas IDs to hemisphere and
        broad structural class (i.e., "cortex", "subcortex", "cerebellum").
        Default: None

    Returns
    -------
    info : pandas.DataFrame
        Loaded dataframe with information on atlas

    Raises
    ------
    ValueError
        If `info` does not have sufficient information
    """
    atlas = check_niimg_3d(atlas)

    # load info, if not already
    if isinstance(info, str):
        info = pd.read_csv(info)

    if not isinstance(info, pd.DataFrame):
        raise ValueError('Provided `info` of type {} is not a filepath or '
                         'DataFrame. Please confirm inputs and try again.'
                         .format(type(info)))

    ids = get_unique_labels(atlas)
    cols = ['id', 'hemisphere', 'structure']
    try:
        assert all(c in info.columns for c in cols)
        assert np.setdiff1d(ids, info.id.values).size == 0
    except AssertionError:
        raise ValueError('Provided `info` does not have adequate information '
                         'on supplied `atlas`. Please confirm that `info` has '
                         'columns [\'id\', \'hemisphere\', \'structure\'], '
                         'and that the region IDs listed in `info` account '
                         'for all those found in `atlas.')

    return info


def check_metric(metric):
    """
    Confirms `metric` is a valid aggregation metric

    Parameters
    ----------
    metric : str or func, optional
        Mechanism by which to reduce arrays. If str, should be in ['mean',
        'median']. If func, should be able to accept an `N`-dimensional input
        and the `axis` keyword argument and return an `N-1`-dimensional output.
        Default: 'mean'

    Returns
    -------
    metric : func
        Mechanism by which to reduce arrays
    """
    if isinstance(metric, str):
        try:
            metric = AGG_FUNCS[metric]
        except KeyError:
            raise ValueError('Provided metric {0} is not valid. If supplied'
                             'as string, metric must be in {1}.'
                             .format(metric, list(AGG_FUNCS.keys())))
    else:
        try:
            test = np.random.rand(10, 10, 10)
            assert metric(test, axis=0).shape == (10, 10)
            assert isinstance(metric(test), float)
        except (AssertionError, TypeError):
            raise TypeError('Provided metric {0} does not perform as '
                            'expected. Please ensure it accepts the `axis` '
                            'keyword argument and can reduce an `N`-'
                            'dimensional input to an `N-1`-dimensional output.'
                            .format(metric))

    return metric


def efficient_corr(x, y):
    """
    Computes correlation of i-th column in `x` with i-th column in `y`

    Parameters
    ----------
    x, y : (N, M) array_like
        Input data arrays

    Returns
    -------
    corr : (M,) numpy.ndarray
        Correlations of columns in `x` and `y`
    """
    corr = np.sum(zscore(x, ddof=1) * zscore(y, ddof=1), axis=0) / (len(x) - 1)

    return corr


def get_unique_labels(label_image):
    """
    Returns all possible ROI labels from ``label_image``

    Parameters
    ----------
    label_image : niimg-like object
        ROI image, where each ROI is identified with a unique integer ID

    Returns
    -------
    labels : np.ndarray
        Integer labels of all ROIS found within ``label_image``
    """

    label_image = check_niimg_3d(label_image)
    return np.trim_zeros(np.unique(label_image.get_data())).astype(int)


def get_centroids(label_image, labels_of_interest=None, image_space=False):
    """
    Finds centroids of ``labels_of_interest`` in ``label_image``

    Parameters
    ----------
    label_image : niimg-like object
        3D image containing integer label at each point
    labels_of_interest : array_like, optional
        List of values containing labels of which to find centroids. Default:
        all possible labels
    image_space : bool, optional
        Whether to return xyz (image space) coordinates for centroids based
        on transformation in ``label_image.affine``. Default: False

    Returns
    -------
    centroids : (3 x N) np.ndarray
        Coordinates of centroids for ROIs in input data
    """

    label_image = check_niimg_3d(label_image)

    # if no labels of interest provided, get all possible labels
    if labels_of_interest is None:
        labels_of_interest = get_unique_labels(label_image)

    # get centroids for all possible labels
    image_data = label_image.get_data()
    centroids = np.row_stack([center_of_mass(image_data == label) for
                              label in labels_of_interest]).T

    # return x,y,z if desired; otherwise, i,j,k
    if image_space:
        return ijk_to_xyz(centroids, label_image.affine)

    return centroids


def closest_centroid(coords, centroids):
    """
    Returns label for parcel with centroid closest to ``coords``

    Computes Euclidean distances between ``coords`` and each centroid in
    ``centroids``, returning index of closest centroid

    Parameters
    ----------
    coords : (3 x 1) array_like
        Coordinates of sample
    centroids : (3 x N) array_like
        Centroids of parcels (in same space as `coords`)

    Returns
    -------
    label : int
        Index of closest centroid in ``centroids``
    """

    distances = np.squeeze(cdist(np.atleast_2d(coords).T, centroids.T))

    return distances.argmin()


def _check_coord_inputs(coords):
    """
    Confirms `coords` are appropriate shape for coordinate transform

    Parameters
    ----------
    coords : array-like

    Returns
    -------
    coords : (4 x N) numpy.ndarray
    """
    coords = np.atleast_2d(coords).T
    if 3 not in coords.shape:
        raise ValueError('Input coordinates must be of shape (3 x N). '
                         'Provided coordinate shape: {}'.format(coords.shape))
    if coords.shape[0] != 3:
        coords = coords.T
    # add constant term to coords to make 4 x N
    coords = np.row_stack([coords, np.ones_like(coords[0])])
    return coords


def ijk_to_xyz(coords, affine):
    """
    Converts `coords` in cartesian space to `affine` space

    Parameters
    ----------
    coords : (N, 3) array_like
        Image coordinate values, where each entry is an ijk coordinate in
        cartesian space
    affine : (4, 4) array-like
        Affine matrix

    Returns
    ------
    xyz : (N, 3) numpy.ndarray
        Provided `coords` in `affine` space
    """
    coords = _check_coord_inputs(coords)
    aff_coords = np.dot(affine, coords)[:3].T
    return aff_coords


def xyz_to_ijk(coords, affine):
    """
    Converts `coords` in `affine` space to cartesian space

    Parameters
    ----------
    coords : (N, 3) array_like
        Image coordinate values, where each entry is an xyz coordinates in
        `affine` space
    affine : (4, 4) array-like
        Affine matrix

    Returns
    ------
    ijk : (N, 3) numpy.ndarray
        Provided `coords` in cartesian space
    """
    coords = _check_coord_inputs(coords)
    ijk_coords = np.linalg.solve(affine, coords)[:3].T.astype(int)
    return ijk_coords


def expand_roi(coords, dilation=1, return_array=True):
    """
    Expands coordinates ``coords`` to include neighboring coordinates

    Computes all possible coordinates of distance ``dilation`` from ``coords``.
    Returns a generator (``itertools.product``) by default, but can return an
    array if desired (if ``return_array=True``).

    Parameters
    ----------
    coords : (3,) array_like
        List of ijk values for coordinate in 3D space
    dilation : int, optional
        How many neighboring voxels to expand around `coords`. Default: 1
    return_array : bool, optional
        Whether to return array instead of generator. Default: True

    Returns
    -------
    coords : (27, 3) generator
        Coordinates of expanded ROI
    """

    def expand(x, d=1):
        return np.arange((x - d), (x + d + 1), dtype=int)

    # return all combinations of coordinates
    coords = np.atleast_2d(coords)
    gen = itertools.product(*[expand(n, d=dilation) for n in coords])

    # coerce to array if desired
    if return_array:
        return np.asarray(list(gen))

    return gen
