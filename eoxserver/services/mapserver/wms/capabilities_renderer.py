#-------------------------------------------------------------------------------
# $Id$
#
# Project: EOxServer <http://eoxserver.org>
# Authors: Fabian Schindler <fabian.schindler@eox.at>
#
#-------------------------------------------------------------------------------
# Copyright (C) 2011 EOX IT Services GmbH
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
#-------------------------------------------------------------------------------

from itertools import chain

from eoxserver.core import Component, implements, ExtensionPoint
from eoxserver.core.config import get_eoxserver_config
from eoxserver.core.util.timetools import isoformat
from eoxserver.contrib.mapserver import create_request, Map, Layer
from eoxserver.resources.coverages import crss
from eoxserver.resources.coverages.formats import getFormatRegistry
from eoxserver.services.ows.common.config import CapabilitiesConfigReader
from eoxserver.services.ows.wms.interfaces import (
    WMSCapabilitiesRendererInterface
)
from eoxserver.services.mapserver.interfaces import LayerFactoryInterface
from eoxserver.services.result import result_set_from_raw_data, get_content_type


class MapServerWMSCapabilitiesRenderer(Component):
    """ WMS Capabilities renderer implementation using MapServer.
    """
    implements(WMSCapabilitiesRendererInterface)

    layer_factories = ExtensionPoint(LayerFactoryInterface)

    @property
    def suffixes(self):
        return list(
            chain(*[factory.suffixes for factory in self.layer_factories])
        )


    def render(self, collections, request_values):
        conf = CapabilitiesConfigReader(get_eoxserver_config())

        suffixes = self.suffixes

        map_ = Map()
        map_.setMetaData({
            "enable_request": "*",
            "onlineresource": conf.http_service_url,
            "service_onlineresource": conf.onlineresource,
            "updateSequence": conf.update_sequence,
            "name": conf.name,
            "title": conf.title,
            "abstract": conf.abstract,
            "accessconstraints": conf.access_constraints,
            "addresstype": "postal",
            "address": conf.delivery_point,
            "stateorprovince": conf.administrative_area,
            "city": conf.city,
            "postcode": conf.postal_code,
            "country": conf.country,
            "contactelectronicmailaddress": conf.electronic_mail_address,
            "contactfacsimiletelephone": conf.phone_facsimile,
            "contactvoicetelephone": conf.phone_voice,
            "contactperson": conf.individual_name,
            "contactorganization": conf.provider_name,
            "contactposition": conf.position_name,
            "fees": conf.fees,
            "keywordlist": ",".join(conf.keywords),
            "srs": " ".join(crss.getSupportedCRS_WCS(format_function=crss.asShortCode)),
        }, namespace="ows")
        map_.setProjection("EPSG:4326")
        map_.setMetaData({
            "getmap_formatlist": ",".join([f.mimeType for f in self.get_wms_formats()]),
            "getfeatureinfo_formatlist": "text/html,application/vnd.ogc.gml,text/plain"
        }, namespace="wms")

        for collection in collections:
            group_name = None
            
            # calculate extent and timextent for every collection
            extent = " ".join(map(str, collection.extent_wgs84))

            eo_objects = collection.eo_objects.filter(
                begin_time__isnull=False, end_time__isnull=False
            )
            timeextent = ",".join(
                map(
                    lambda o: (
                        "/".join(
                            map(isoformat, o.time_extent)
                        ) + "/PT1S"
                    ), eo_objects
                )
            )

            if len(suffixes) > 1:
                # create group layer, if there is more than one suffix for this 
                # collection
                group_name = collection.identifier + "_group"
                group_layer = Layer(group_name)
                group_layer.setMetaData({
                    "title": group_name,
                    "extent": extent
                }, namespace="wms")
                map_.insertLayer(group_layer)

            for suffix in suffixes:
                layer_name = collection.identifier + (suffix or "")
                layer = Layer(layer_name)
                if group_name:
                    layer.setMetaData({
                        "layer_group": "/" + group_name
                    }, namespace="wms")

                layer.setMetaData({
                    "title": layer_name,
                    "extent": extent,
                    "timeextent": timeextent
                }, namespace="wms")
                map_.insertLayer(layer)
        
        request = create_request(request_values)
        raw_result = map_.dispatch(request)
        result = result_set_from_raw_data(raw_result)
        return result, get_content_type(result)

    def get_wms_formats(self):
        return getFormatRegistry().getSupportedFormatsWMS()
