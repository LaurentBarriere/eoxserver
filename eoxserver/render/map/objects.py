# ------------------------------------------------------------------------------
#
# Project: EOxServer <http://eoxserver.org>
# Authors: Fabian Schindler <fabian.schindler@eox.at>
#
# ------------------------------------------------------------------------------
# Copyright (C) 2017 EOX IT Services GmbH
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies of this Software or works derived from this Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
# ------------------------------------------------------------------------------


class Layer(object):
    """ Abstract layer
    """
    def __init__(self, name, style):
        self._name = name
        self._style = style

    @property
    def name(self):
        return self._name

    @property
    def style(self):
        return self._style


class CoverageLayer(Layer):
    """ Representation of a coverage layer.
    """
    def __init__(self, name, style, coverage, bands, wavelengths, time,
                 elevation):
        super(CoverageLayer, self).__init__(name, style)
        self._coverage = coverage
        self._bands = bands
        self._wavelengths = wavelengths
        self._time = time
        self._elevation = elevation

    @property
    def coverage(self):
        return self._coverage

    @property
    def bands(self):
        return self._bands

    @property
    def wavelengths(self):
        return self._wavelengths

    @property
    def time(self):
        return self._time

    @property
    def elevation(self):
        return self._elevation


class CoverageMosaicLayer(Layer):
    def __init__(self, name, style, coverages, bands, wavelengths):
        super(CoverageMosaicLayer, self).__init__(name, style)
        self._coverages = coverages
        self._bands = bands
        self._wavelengths = wavelengths

    @property
    def coverages(self):
        return self._coverages

    @property
    def bands(self):
        return self._bands

    @property
    def wavelengths(self):
        return self._wavelengths


class BrowseLayer(Layer):
    """ Representation of a browse layer.
    """
    def __init__(self, name, style, browses):
        super(BrowseLayer, self).__init__(name, style)
        self._browses = browses

    @property
    def browses(self):
        return self._browses


class MaskLayer(Layer):
    """ Representation of a mask layer.
    """
    def __init__(self, name, style, masks):
        super(MaskLayer, self).__init__(name, style)
        self._masks = masks

    @property
    def masks(self):
        return self._masks


class MaskedBrowseLayer(Layer):
    """ Representation of a layer.
    """
    def __init__(self, name, style, masked_browses):
        super(MaskedBrowseLayer, self).__init__(name, style)
        self._masked_browses = masked_browses

    @property
    def masked_browses(self):
        return self._masked_browses


class OutlinesLayer(Layer):
    """ Representation of a layer.
    """
    def __init__(self, name, style, footprints):
        super(OutlinesLayer, self).__init__(name, style)
        self._footprints = footprints

    @property
    def footprints(self):
        return self._footprints


class Map(object):
    """ Abstract interpretation of a map to be drawn.
    """
    def __init__(self, layers, width, height, format, bbox, crs, bgcolor=None,
                 transparent=True, time=None, elevation=None):
        self._layers = layers
        self._width = int(width)
        self._height = int(height)
        self._format = format
        self._bbox = bbox
        self._crs = crs
        self._bgcolor = bgcolor
        self._transparent = transparent
        self._time = time
        self._elevation = elevation

    @property
    def layers(self):
        return self._layers

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def format(self):
        return self._format

    @property
    def bbox(self):
        return self._bbox

    @property
    def crs(self):
        return self._crs

    @property
    def bgcolor(self):
        return self._bgcolor

    @property
    def transparent(self):
        return self._transparent

    @property
    def time(self):
        return self._time

    @property
    def elevation(self):
        return self._elevation

    def __repr__(self):
        return (
            'Map: %r '
            'width=%r '
            'height=%r '
            'format=%r '
            'bbox=%r '
            'crs=%r '
            'bgcolor=%r '
            'transparent=%r '
            'time=%r '
            'elevation=%r' % (
                self.layers, self.width, self.height, self.format, self.bbox,
                self.crs, self.bgcolor, self.transparent, self.time,
                self.elevation,
            )
        )
