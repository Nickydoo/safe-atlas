import os
import json

from matplotlib import pyplot as plt
from humanize import naturalsize as sz

import numpy as np

# import rasterio's tools
import rasterio
from rasterio.plot import show as rasterio_show
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform
from rasterio.warp import reproject as rasterio_reproject

# Pretty print
import pprint
pp = pprint.PrettyPrinter(depth=4)


def load(src_path):
    """
        Loads imagery as a rasterio object
    """
    satdat = rasterio.open(src_path)
    return satdat


def show(satdat):
    """
        Display satdat as matplotlib figure
    """

    # check input
    if(type(satdat) != rasterio.io.DatasetReader):
        raise Exception('Wrong Format')

    rasterio_show(satdat)


def info(satdat):
    """
        Display General Info about the satdat
    """

    # check input
    if(type(satdat) != rasterio.io.DatasetReader):
        raise Exception('Wrong Format')

    # dataset name
    print(f'Dataset Name : {satdat.name}\n')

    # number of bands in this dataset
    print(f'Number of Bands : {satdat.count}\n')

    # The dataset reports a band count.
    print(f'Number of Bands according to dataset : {satdat.count}\n')

    # And provides a sequence of band indexes.  These are one indexing, not zero indexing like Numpy arrays.
    print(f'Bands indexes : {satdat.indexes}\n')

    # Minimum bounding box in projected units
    print(f'Min Bounding Box : {satdat.bounds}\n')

    # Get dimensions, in map units
    width_in_projected_units = abs(satdat.bounds.right - satdat.bounds.left)
    height_in_projected_units = abs(satdat.bounds.top - satdat.bounds.bottom)
    print(f"Width: {width_in_projected_units}, Height: {height_in_projected_units}\n")

    # Number of rows and columns.
    print(f"Rows: {satdat.height}, Columns: {satdat.width}\n")

    # This dataset's projection uses meters as distance units.  What are the dimensions of a single pixel in meters?
    xres = width_in_projected_units / satdat.width
    yres = height_in_projected_units / satdat.height
    print(f'Width of pixel (in m) : {xres}')
    print(f'Height of pixel (in m) : {yres}')
    print(f"Are the pixels square: {xres == yres}\n")

    # Get coordinate reference system
    print(f'Coordinates System : {satdat.crs}\n')

    # Convert pixel coordinates to world coordinates.
    # Upper left pixel
    row_min = 0
    col_min = 0

    # Lower right pixel.  Rows and columns are zero indexing.
    row_max = satdat.height - 1
    col_max = satdat.width - 1

    # Transform coordinates with the dataset's affine transformation.
    topleft = satdat.transform * (row_min, col_min)
    botright = satdat.transform * (row_max, col_max)

    print(f"Top left corner coordinates: {topleft}")
    print(f"Bottom right corner coordinates: {botright}\n")

    # All of the metadata required to create an image of the same dimensions, datatype, format, etc. is stored in
    # the dataset's profile:
    pp.pprint(satdat.profile)
    print('\n')


def compress(src_path, out_path, compression_type='JPEG'):
    """
        Compress imagery to reduce filesize

        Raster datasets use compression to reduce filesize. There are a number of compression methods,
        all of which fall into two categories: lossy and lossless. Lossless compression methods retain
        the original values in each pixel of the raster, while lossy methods result in some values
        being removed. Because of this, lossy compression is generally not well-suited for analytic
        purposes, but can be very useful for reducing storage size of visual imagery.

        By creating a lossy-compressed copy of a visual asset, we can significantly reduce the
        dataset's filesize. In this example, we will create a copy using the "JPEG" lossy compression method
    """

    # get initial size in bytes
    init_size = os.path.getsize(src_path)

    # load file
    satdat = load(src_path)

    # read all bands from source dataset into a single 3-dimensional ndarray
    data = satdat.read()

    # write new file using profile metadata from original dataset and specifying compression type
    profile = satdat.profile
    profile['compress'] = compression_type

    with rasterio.open(out_path, 'w', **profile) as dst:
        dst.write(data)

    # returns size in bytes
    final_size = os.path.getsize(out_path)

    # compute diff
    ratio = round(10000.0*final_size/float(init_size))/100.0

    # output a human-friendly size
    print(f'(Initial size, Final Size, Ratio) : ({sz(init_size)}, {sz(final_size)}, {ratio}%)\n')


def to_uint8(src_path, out_path, min=0, max=10000):
    """
        Takes an image and converts the data type to uint8 by scaling down the pixel values
    """

    # load file
    satdat = load(src_path)

    # read all bands from source dataset into a single ndarray
    bands = satdat.read()

    def scale(band):
        if(np.max(band) > 255):
            band = np.round((band / 10000.0)*255.0)     # scale to 0 - 255
            band[band > 255] = 255                      # if above set to max
        return band

    # scale each band
    for i, band in enumerate(bands):
        bands[i] = scale(band).astype(np.uint8)

    # get count
    count = len(bands)

    # stack
    scaled_img = np.dstack(bands).astype(np.uint8)

    # move axis with entries to beginning
    scaled_img = np.moveaxis(scaled_img,-1,0)

    # get the metadata of original GeoTIFF:
    meta = satdat.meta

    # get the dtype
    m_dtype = scaled_img.dtype

    # set the source metadata as kwargs we'll use to write the new data:
    kwargs = meta

    # update the 'dtype' value to match our NDVI array's dtype:
    kwargs.update(dtype=m_dtype)

    # update the 'count' value since our output will no longer be a 4-band image:
    kwargs.update(count=count)

    # Finally, use rasterio to write new raster file 'data/ndvi.tif':
    with rasterio.open(out_path, 'w', **kwargs) as dst:
            dst.write(scaled_img)


def bbox_to_corners(bbox_geometry):
    """
        Takes a postgis Box2D as input and returns the corners in the [xMin, yMin, xMax, yMax] order
    """

    # cast as str
    geometry = str(bbox_geometry)

    # parse
    geometry = geometry.split('(')[-1]
    geometry = geometry.replace(')', '')
    geometry = geometry.strip()

    # split points
    points = geometry.split(',')
    if(len(points) != 2):
        raise Exception('Input bounding box is invalid')

    # go through points
    clean_pts = []
    for point in points:

        # split lat/lng
        point = point.strip()
        lng_lat = point.split(' ')
        if(len(lng_lat) != 2):
            raise Exception('Input point is invalid')

        # parse
        lng, lat = lng_lat
        lng = lng.strip()
        lat = lat.strip()
        lat = float(lat)
        lng = float(lng)

        # append
        clean_pts.append([lng, lat])

    # check
    if(len(clean_pts) != 2):
        raise Exception('Invalid bbox after processing')

    # grab corners
    MIN_X = clean_pts[0][0]
    MIN_Y = clean_pts[0][1]
    MAX_X = clean_pts[1][0]
    MAX_Y = clean_pts[1][1]

    return [MIN_X, MIN_Y, MAX_X, MAX_Y]


def point_to_lng_lat(point_geometry):
    """
        Takes a postgis Point as input and returns the latitude and longitude in the [lng, lat] order
    """

    # cast as str
    point = str(point_geometry)

    # parse
    point = point.split('(')[-1]
    point = point.replace(')', '')

    # split lat/lng
    point = point.strip()
    lng_lat = point.split(' ')
    if(len(lng_lat) != 2):
        raise Exception('Input point is invalid')

    # parse
    lng, lat = lng_lat
    lng = lng.strip()
    lat = lat.strip()
    lat = float(lat)
    lng = float(lng)

    return [lng, lat]


def bbox_to_GeoJSON(bbox_geometry, bbox_crs, out_path=None):
    """
        Takes a postgis Box2D as input and returns the GeoJSON
    """

    # convert postgis bbox to corners array
    corners = bbox_to_corners(bbox_geometry)

    # convert bbox to json
    geojson = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {
                "name": f"urn:ogc:def:crs:EPSG::{bbox_crs}"
            }
        },
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [corners[0], corners[1]],
                            [corners[2], corners[1]],
                            [corners[2], corners[3]],
                            [corners[0], corners[3]],
                            [corners[0], corners[1]]
                        ]
                    ]
                }
            }
        ]
    }

    # save geojson json
    if(out_path is not None):
        with open(out_path, 'w') as outfile:
            json.dump(geojson, outfile)

    return geojson


def point_to_GeoJSON(point_geometry, point_crs, out_path=None):
    """
        Takes a postgis Point as input and returns the GeoJSON
    """

    # convert postgis bbox to corners array
    lng, lat = point_to_lng_lat(point_geometry)

    # convert point to json
    geojson = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {
                "name": f"urn:ogc:def:crs:EPSG::{point_crs}"
            }
        },
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        [lng, lat]
                    ]
                }
            }
        ]
    }

    # save geojson json
    if(out_path is not None):
        with open(out_path, 'w') as outfile:
            json.dump(geojson, outfile)

    return geojson


def convert_lng_lat_to_pixel(satdat, lng, lat):
    """
        Maps a (lng, lat) point to a pixel (x, y) point
    """

    # check if inside
    if(lng > satdat.bounds.right or lng < satdat.bounds.left):
        raise Exception('Invalid lat/lng')
    if(lat > satdat.bounds.top or lat < satdat.bounds.bottom):
        raise Exception('Invalid lat/lng')

    # Get dimensions, in map units
    width_in_projected_units = np.abs(satdat.bounds.right - satdat.bounds.left)
    height_in_projected_units = np.abs(satdat.bounds.top - satdat.bounds.bottom)

    # compute
    xres = satdat.width/float(width_in_projected_units)
    yres = satdat.height/float(height_in_projected_units)
    xpos = (satdat.bounds.right-lng)*xres
    ypos = (satdat.bounds.top-lat)*yres

    # round
    xpos = int(xpos)
    ypos = int(ypos)

    return xpos, ypos


def crop(src_path, out_path, bbox_geometry, bbox_crs):
    """
        Crop imagery using a Postgis Box2d geometry
    """

    # validate area of interest


    # load imagery
    satdata = rasterio.open(src_path)

    # grab crs
    crs = satdata.meta['crs']
    crs = str(crs).split(':')[-1]

    # check crs
    if(crs != bbox_crs):
        raise Exception(f'Imagery & bounding box crs mismatch ({crs}, {bbox_crs})')

    # apply mask with crop=True to crop the resulting raster to the AOI's bounding box
    clipped, transform = mask(satdata, aoi, crop=True)

    # Using a copy of the metadata from our original raster dataset, we can write a new geoTIFF
    # containing the new, clipped raster data:
    meta = satdata.meta.copy()

    # update metadata with new, clipped mosaic's boundaries
    meta.update(
        {
            "transform": transform,
            "height":clipped.shape[1],
            "width":clipped.shape[2]
        }
    )

    # write the clipped-and-cropped dataset to a new GeoTIFF
    with rasterio.open(out_path, 'w', **meta) as dst:
        dst.write(clipped)


def reproject(src_path, out_path, target_crs='EPSG:4326'):
    """
        Reprojects the imagery to a new coordinate system

        In order to translate pixel coordinates in a raster dataset into coordinates that use a
        spatial reference system, an **affine transformation** must be applied to the dataset.
        This **transform** is a matrix used to translate rows and columns of pixels into (x,y)
        spatial coordinate pairs. Every spatially referenced raster dataset has an affine transform
        that describes its pixel-to-map-coordinate transformation.

        In order to reproject a raster dataset from one coordinate reference system to another,
        rasterio uses the **transform** of the dataset: this can be calculated automatically using
        rasterio's `calculate_default_transform` method:

        target CRS: rasterio will accept any CRS that can be defined using WKT
    """

    # load satdata
    satdata = load(src_path)

    # calculate a transform and new dimensions using our dataset's current CRS and dimensions
    transform, width, height = calculate_default_transform(satdata.crs,
                                                        target_crs,
                                                        satdata.width,
                                                        satdata.height,
                                                        *satdata.bounds)

    # Using a copy of the metadata from the clipped raster dataset and the transform we defined above,
    # we can write a new geoTIFF containing the reprojected and clipped raster data:
    metadata = satdata.meta.copy()

    # Change the CRS, transform, and dimensions in metadata to match our desired output dataset
    metadata.update({'crs':target_crs,
                    'transform':transform,
                    'width':width,
                    'height':height})

    # apply the transform & metadata to perform the reprojection
    with rasterio.open(out_path, 'w', **metadata) as reprojected:
        for band in range(1, satdata.count + 1):
            rasterio_reproject(
                source=rasterio.band(satdata, band),
                destination=rasterio.band(reprojected, band),
                src_transform=satdata.transform,
                src_crs=satdata.crs,
                dst_transform=transform,
                dst_crs=target_crs
            )
