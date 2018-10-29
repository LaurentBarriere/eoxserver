#-------------------------------------------------------------------------------
#
# Project: EOxServer <http://eoxserver.org>
# Authors: Fabian Schindler <fabian.schindler@eox.at>
#
#-------------------------------------------------------------------------------
# Copyright (C) 2013 EOX IT Services GmbH
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
from lxml import etree

from django.contrib.gis.geos import Polygon
from django.utils.timezone import now

from eoxserver.contrib import gdal, vsi
from eoxserver.backends.access import get_vsi_path
from eoxserver.core.config import get_eoxserver_config
from eoxserver.core.util.timetools import isoformat
from eoxserver.backends.access import retrieve
from eoxserver.contrib.osr import SpatialReference
# from eoxserver.resources.coverages.models import (
#     RectifiedStitchedMosaic, ReferenceableDataset
# )
from eoxserver.resources.coverages.formats import getFormatRegistry
from eoxserver.resources.coverages import crss
from eoxserver.services.gml.v32.encoders import GML32Encoder, EOP20Encoder
from eoxserver.services.ows.component import ServiceComponent, env
from eoxserver.services.ows.common.config import CapabilitiesConfigReader
from eoxserver.services.ows.common.v20.encoders import OWS20Encoder
from eoxserver.services.ows.wcs.v21.util import (
    nsmap, ns_xlink, ns_gml, ns_wcs, ns_eowcs,
    OWS, GML, GMLCOV, CIS, WCS, CRS, EOWCS, SWE, INT, SUPPORTED_INTERPOLATIONS
)
from eoxserver.services.urls import get_http_service_url

PROFILES = [
    "spec/WCS_application-profile_earth-observation/1.0/conf/eowcs",
    "spec/WCS_application-profile_earth-observation/1.0/conf/eowcs_get-kvp",
    "spec/WCS_service-extension_crs/1.0/conf/crs",
    "spec/WCS/2.1/conf/core",
    "spec/WCS_protocol-binding_get-kvp/1.0/conf/get-kvp",
    "spec/WCS_protocol-binding_post-xml/1.0/conf/post-xml",
    "spec/GMLCOV/1.0/conf/gml-coverage",
    "spec/GMLCOV/1.0/conf/multipart",
    "spec/GMLCOV/1.0/conf/special-format",
    "spec/GMLCOV_geotiff-coverages/1.0/conf/geotiff-coverage",
    "spec/WCS_geotiff-coverages/1.0/conf/geotiff-coverage",
    "spec/WCS_service-model_crs-predefined/1.0/conf/crs-predefined",
    "spec/WCS_service-extension_interpolation/1.0/conf/interpolation",
    "spec/WCS_service-extension_range-subsetting/1.0/conf/record-subsetting",
    "spec/WCS_service-extension_scaling/1.0/conf/scaling",
]


class WCS21BaseXMLEncoder(object):
    def get_coverage_subtype(self, coverage):
        subtype = "RectifiedDataset"
        if not coverage.footprint or not coverage.begin_time or \
                not coverage.end_time:
            subtype = "RectifiedGridCoverage"
        elif coverage.grid and coverage.grid.axis_1_offset is None:
            subtype = "ReferenceableDataset"

        return subtype


class WCS21CapabilitiesXMLEncoder(WCS21BaseXMLEncoder, OWS20Encoder):
    def encode_service_metadata(self):
        service_metadata = WCS("ServiceMetadata")

        # get the list of enabled formats from the format registry
        formats = filter(
            lambda f: f, getFormatRegistry().getSupportedFormatsWCS()
        )
        service_metadata.extend(
            map(lambda f: WCS("formatSupported", f.mimeType), formats)
        )

        # get a list of supported CRSs from the CRS registry
        supported_crss = crss.getSupportedCRS_WCS(
            format_function=crss.asURL
        )
        extension = WCS("Extension")
        service_metadata.append(extension)
        crs_metadata = CRS("CrsMetadata")
        extension.append(crs_metadata)
        crs_metadata.extend(
            map(lambda c: CRS("crsSupported", c), supported_crss)
        )

        base_url = "http://www.opengis.net/def/interpolation/OGC/1/"

        extension.append(
            INT("InterpolationMetadata", *[
                INT("InterpolationSupported",
                    base_url + supported_interpolation
                ) for supported_interpolation in SUPPORTED_INTERPOLATIONS
            ])
        )
        return service_metadata

    def encode_contents(self, coverages_qs, dataset_series_qs):
        contents = []

        # reduce data transfer by only selecting required elements
        coverages_qs = coverages_qs.only(
             "identifier", "begin_time", "end_time", "footprint", "grid"
        ).select_related('grid')
        coverages = list(coverages_qs)

        if coverages:
            contents.extend([
                WCS("CoverageSummary",
                    WCS("CoverageId", coverage.identifier),
                    WCS("CoverageSubtype",
                        self.get_coverage_subtype(coverage)
                    )
                ) for coverage in coverages
            ])

        # reduce data transfer by only selecting required elements
        dataset_series_qs = dataset_series_qs.only(
           "identifier", "begin_time", "end_time", "footprint"
        )
        dataset_series_set = list(dataset_series_qs)
        if dataset_series_set:
            dataset_series_elements = []
            for dataset_series in dataset_series_qs:
                footprint = dataset_series.footprint
                dataset_series_summary = EOWCS("DatasetSeriesSummary")

                # NOTE: non-standard, ows:WGS84BoundingBox is actually mandatory,
                # but not available for e.g: empty collections
                if footprint:
                    minx, miny, maxx, maxy = footprint.extent
                    dataset_series_summary.append(
                        OWS("WGS84BoundingBox",
                            OWS("LowerCorner", "%f %f" % (miny, minx)),
                            OWS("UpperCorner", "%f %f" % (maxy, maxx)),
                        )
                    )

                dataset_series_summary.append(
                    EOWCS("DatasetSeriesId", dataset_series.identifier)
                )

                # NOTE: non-standard, gml:TimePosition is actually mandatory,
                # but not available for e.g: empty collections
                if dataset_series.begin_time and dataset_series.end_time:
                    dataset_series_summary.append(
                        GML("TimePeriod",
                            GML(
                                "beginPosition",
                                isoformat(dataset_series.begin_time)
                            ),
                            GML(
                                "endPosition",
                                isoformat(dataset_series.end_time)
                            ),
                            **{
                                ns_gml("id"): dataset_series.identifier +
                                "_timeperiod"
                            }
                        )
                    )

                dataset_series_elements.append(dataset_series_summary)

            contents.append(WCS("Extension", *dataset_series_elements))

        return WCS("Contents", *contents)

    def encode_capabilities(self, sections, coverages_qs=None,
                            dataset_series_qs=None, request=None):
        conf = CapabilitiesConfigReader(get_eoxserver_config())

        all_sections = "all" in sections
        caps = []
        if all_sections or "serviceidentification" in sections:
            caps.append(self.encode_service_identification(
                "WCS", conf, PROFILES
            ))

        if all_sections or "serviceprovider" in sections:
            caps.append(self.encode_service_provider(conf))

        if all_sections or "operationsmetadata" in sections:
            caps.append(self.encode_operations_metadata(
                request, "WCS", ("2.1.0", )
            ))

        if all_sections or "servicemetadata" in sections:
            caps.append(self.encode_service_metadata())

        inc_contents = all_sections or "contents" in sections
        inc_coverage_summary = inc_contents or "coveragesummary" in sections
        inc_dataset_series_summary = (
            inc_contents or "datasetseriessummary" in sections
        )

        if inc_contents or inc_coverage_summary or inc_dataset_series_summary:
            caps.append(
                self.encode_contents(
                    coverages_qs if inc_coverage_summary else None,
                    dataset_series_qs if inc_dataset_series_summary else None
                )
            )

        return WCS(
            "Capabilities", *caps, version="2.1.0",
            updateSequence=conf.update_sequence
        )

    def get_schema_locations(self):
        return nsmap.schema_locations


class CIS10Encoder(WCS21BaseXMLEncoder, GML32Encoder):
    def __init__(self, *args, **kwargs):
        self._cache = {}

    def get_gml_id(self, identifier):
        if identifier[0].isdigit():
            return "gmlid_%s" % identifier
        return identifier

    def encode_grid_envelope(self, sizes):
        return GML("GridEnvelope",
            GML("low", " ".join("0" for size in sizes)),
            GML("high", " ".join(("%d" % (size - 1) for size in sizes)))
        )

    def encode_rectified_grid(self, grid, coverage, name):
        axis_names = [axis.name for axis in grid]
        offsets = [axis.offset for axis in grid]
        origin = coverage.origin

        sr = SpatialReference(grid.coordinate_reference_system)
        url = sr.url

        offset_vectors = [
            GML("offsetVector",
                " ".join(["0"] * i + [str(offset)] + ["0"] * (len(offsets) - i)),
                srsName=url
            )
            for i, offset in enumerate(offsets)
        ]

        if crss.hasSwappedAxes(sr.srid):
            axis_names[0:2] = [axis_names[1], axis_names[0]]
            offset_vectors[0:2] = [offset_vectors[1], offset_vectors[0]]
            origin[0:2] = [origin[1], origin[0]]

        return GML("RectifiedGrid",
            GML("limits",
                self.encode_grid_envelope(coverage.size)
            ),
            GML("axisLabels", " ".join(axis_names)),
            GML("origin",
                GML("Point",
                    GML("pos", " ".join(str(o) for o in origin)),
                    **{
                        ns_gml("id"): self.get_gml_id("%s_origin" % name),
                        "srsName": url
                    }
                )
            ),
            *offset_vectors,
            **{
                ns_gml("id"): self.get_gml_id(name),
                "dimension": "2"
            }
        )

    def encode_referenceable_grid(self, coverage, grid_name):
        size_x, size_y = size
        swap = crss.getAxesSwapper(sr.srid)
        labels = ("x", "y") if sr.IsProjected() else ("long", "lat")
        axis_labels = " ".join(swap(*labels))

        return GML("ReferenceableGrid",
            GML("limits",
                self.encode_grid_envelope(0, 0, size_x - 1, size_y - 1)
            ),
            GML("axisLabels", axis_labels),
            **{
                ns_gml("id"): self.get_gml_id(grid_name),
                "dimension": "2"
            }
        )

    def encode_domain_set(self, coverage, srid=None, size=None, extent=None,
                          rectified=True):
        grid_name = "%s_grid" % coverage.identifier
        grid = coverage.grid
        # srs = SpatialReference(srid) if srid is not None else None

        if grid:
            return GML("domainSet",
                self.encode_rectified_grid(
                    grid, coverage, grid_name
                )
            )
        # else:
        #     return GML("domainSet",
        #         self.encode_referenceable_grid(
        #             size or coverage.size, srs or coverage.spatial_reference,
        #             grid_name
        #         )
        #     )

    def encode_envelope(self, coverage, grid=None):
        # if grid is None:
        footprint = coverage.footprint
        if footprint:
            minx, miny, maxx, maxy = footprint.extent
            sr = SpatialReference(4326)
            swap = crss.getAxesSwapper(sr.srid)
            labels = ("x", "y") if sr.IsProjected() else ("long", "lat")
            axis_labels = " ".join(swap(*labels))
            axis_units = "m m" if sr.IsProjected() else "deg deg"
            frmt = "%.3f %.3f" if sr.IsProjected() else "%.8f %.8f"

            # Make sure values are outside of actual extent
            if sr.IsProjected():
                minx -= 0.0005
                miny -= 0.0005
                maxx += 0.0005
                maxy += 0.0005
            else:
                minx -= 0.000000005
                miny -= 0.000000005
                maxx += 0.000000005
                maxy += 0.000000005

            lower_corner = frmt % swap(minx, miny)
            upper_corner = frmt % swap(maxx, maxy)
            srs_name = sr.url

        elif grid:
            sr = SpatialReference(grid.coordinate_reference_system)
            labels = grid.names
            axis_units = " ".join(
                ["m" if sr.IsProjected() else "deg"] * len(labels)
            )
            extent = list(coverage.extent)

            lc = extent[:len(extent) / 2]
            uc = extent[len(extent) / 2:]

            if crss.hasSwappedAxes(sr.srid):
                labels[0:2] = labels[1], labels[0]
                lc[0:2] = lc[1], lc[0]
                uc[0:2] = uc[1], uc[0]

            frmt = " ".join(
                ["%.3f" if sr.IsProjected() else "%.8f"] * len(labels)
            )

            lower_corner = frmt % tuple(lc)
            upper_corner = frmt % tuple(uc)
            axis_labels = " ".join(labels)
            srs_name = sr.url

        else:
            lower_corner = ""
            upper_corner = ""
            srs_name = ""
            axis_labels = ""
            axis_units = ""

        return GML("boundedBy",
            GML("Envelope",
                GML("lowerCorner", lower_corner),
                GML("upperCorner", upper_corner),
                srsName=srs_name, axisLabels=axis_labels, uomLabels=axis_units,
                srsDimension="2"
            )
        )

    def encode_nil_values(self, nil_values):
        return SWE("nilValues",
            SWE("NilValues",
                *[
                    SWE("nilValue", nil_value[0], reason=nil_value[1])
                    for nil_value in nil_values
                ]
            )
        )

    def encode_field(self, field):
        return SWE("field",
            SWE("Quantity",
                SWE("description", field.description),
                self.encode_nil_values(field.nil_values),
                SWE("uom", code=field.unit_of_measure),
                SWE("constraint",
                    SWE("AllowedValues",
                        *[
                            SWE("interval", "%s %s" % value_range)
                            for value_range in field.allowed_values
                        ] + [
                            SWE("significantFigures", str(
                                field.significant_figures
                            ))
                        ] if field.significant_figures else []
                    )
                ),
                # TODO: lookup correct definition according to data type:
                # http://www.opengis.net/def/dataType/OGC/0/
                definition=field.definition
            ),
            name=field.identifier
        )

    def encode_range_type(self, range_type):
        return GMLCOV("rangeType",
            SWE("DataRecord",
                *[self.encode_field(band) for band in range_type]
            )
        )


class CIS11Encoder(CIS10Encoder):

    def encode_referenceable_grid(self, size):
        size_x, size_y = size

        return CIS(
            "GeneralGrid",
            CIS(
                "IrregularAxisNest",
                **{
                    "axisLabels": "Lat Long date",
                    "uomLabels": "deg deg d",
                }
            ),
            CIS(
                "DisplacementAxisNest",
                **{
                    "axisLabels": "h",
                    "uomLabels": "m",
                }
            ),
            CIS(
                "GridLimits",
                CIS(
                    "IndexAxis",
                    **{
                        "axisLabel": "i",
                        "lowerBound": str(0),
                        "upperBound": str(size_x-1),
                    }
                ),
                CIS(
                    "IndexAxis",
                    **{
                        "axisLabel": "j",
                        "lowerBound": str(0),
                        "upperBound": str(size_y-1),
                    }
                ),
                **{
                    "srsName": "http://www.opengis.net/def/crs/OGC/0/Index2D",
                    "axisLabels": "i j",
                }
            ),
            **{
                "srsName": "http://www.opengis.net/def/crs-compound?1=http://www.opengis.net/def/crs/EPSG/0/4979&amp;2=http://www.opengis.net/def/crs/OGC/0/AnsiDate",
                "axisLabels": "Lat Long h date",
            }
        )

    def encode_domain_set(self, coverage, srid=None, size=None, extent=None,
                          rectified=True):
        grid_name = "%s_grid" % coverage.identifier
        grid = coverage.grid
        # srs = SpatialReference(srid) if srid is not None else None

        if rectified:
            return GML("domainSet",
                self.encode_rectified_grid(
                    grid, coverage, grid_name
                )
            )
        else:
            return CIS("DomainSet",
                self.encode_referenceable_grid(
                    size or coverage.size,
                )
            )

    def encode_envelope(self, coverage, grid=None):
        # if grid is None:
        footprint = coverage.footprint
        if footprint:
            minx, miny, maxx, maxy = footprint.extent
            sr = SpatialReference(4326)
            swap = crss.getAxesSwapper(sr.srid)
            labels = ("x", "y") if sr.IsProjected() else ("long", "lat")
            axis_labels = " ".join(swap(*labels))
            axis_units = "m m" if sr.IsProjected() else "deg deg"
            frmt = "%.3f %.3f" if sr.IsProjected() else "%.8f %.8f"

            # Make sure values are outside of actual extent
            if sr.IsProjected():
                minx -= 0.0005
                miny -= 0.0005
                maxx += 0.0005
                maxy += 0.0005
            else:
                minx -= 0.000000005
                miny -= 0.000000005
                maxx += 0.000000005
                maxy += 0.000000005

            lower_corner = frmt % swap(minx, miny)
            upper_corner = frmt % swap(maxx, maxy)
            srs_name = sr.url

        elif grid:
            sr = SpatialReference(grid.coordinate_reference_system)
            labels = grid.names
            axis_units = " ".join(
                ["m" if sr.IsProjected() else "deg"] * len(labels)
            )
            extent = list(coverage.extent)

            lc = extent[:len(extent) / 2]
            uc = extent[len(extent) / 2:]

            if crss.hasSwappedAxes(sr.srid):
                labels[0:2] = labels[1], labels[0]
                lc[0:2] = lc[1], lc[0]
                uc[0:2] = uc[1], uc[0]

            frmt = " ".join(
                ["%.3f" if sr.IsProjected() else "%.8f"] * len(labels)
            )

            lower_corner = frmt % tuple(lc)
            upper_corner = frmt % tuple(uc)
            axis_labels = " ".join(labels)
            srs_name = sr.url

        else:
            lower_corner = ""
            upper_corner = ""
            srs_name = ""
            axis_labels = ""
            axis_units = ""

        # return CIS("Envelope",
        #     GML("lowerCorner", lower_corner),
        #     GML("upperCorner", upper_corner),
        #     srsName=srs_name, axisLabels=axis_labels, uomLabels=axis_units,
        #     srsDimension="2"
        # )

        return CIS(
            "Envelope",
            CIS(
                "AxisExtent",
                **{
                    "axisLabel": "Lat",
                    "uomLabel": "deg",
                    "lowerBound": str(minx),
                    "upperBound": str(maxx)
                }
            ),
            CIS(
                "AxisExtent",
                **{
                    "axisLabel": "Long",
                    "uomLabel": "deg",
                    "lowerBound": str(miny),
                    "upperBound": str(maxy)
                }
            ),
            CIS(
                "AxisExtent",
                **{
                    "axisLabel": "h",
                    "uomLabel": "m",
                    "lowerBound": "-4917",
                    "upperBound": "25062"
                }
            ),
            CIS(
                "AxisExtent",
                **{
                    "axisLabel": "date",
                    "uomLabel": "d",
                    "lowerBound": str(coverage.begin_time),
                    "upperBound": str(coverage.end_time)
                }
            ),
            **{
                "srsName": "http://www.opengis.net/def/crs-compound?1=http://www.opengis.net/def/crs/EPSG/0/4979&amp;2=http://www.opengis.net/def/crs/OGC/0/AnsiDate",
                "axisLabels": "Lat Long h date",
                "srsDimension": "4",
            }
        )

    def encode_range_type(self, range_type):
        return CIS("rangeType",
            SWE("DataRecord",
                *[self.encode_field(band) for band in range_type]
            )
        )


class WCS21CoverageDescriptionXMLEncoder(CIS11Encoder):
    def encode_coverage_description(self, coverage):
        grid = coverage.grid

        return WCS("CoverageDescription",
            self.encode_envelope(coverage, grid),
            self.encode_domain_set(coverage, rectified=(grid is not None)),
            self.encode_range_type(coverage.range_type),
            WCS("ServiceParameters",
                WCS("CoverageSubtype", self.get_coverage_subtype(coverage))
            ),
            **{ns_gml("id"): self.get_gml_id(coverage.identifier)}
        )

    def encode_coverage_descriptions(self, coverages):
        return WCS("CoverageDescriptions", *[
            self.encode_coverage_description(coverage)
            for coverage in coverages
        ])

    def get_schema_locations(self):
        return {ns_wcs.uri: ns_wcs.schema_location}


class WCS21EOXMLEncoder(WCS21CoverageDescriptionXMLEncoder, EOP20Encoder,
                        OWS20Encoder):
    def encode_eo_metadata(self, coverage, request=None, subset_polygon=None):
        metadata_items = [
            metadata_location
            for metadata_location in coverage.metadata_locations
            if metadata_location.format == "eogml"
        ]
        if len(metadata_items) >= 1:
            with vsi.open(metadata_items[0].path) as f:
                earth_observation = etree.parse(f).getroot()

            if subset_polygon:
                try:
                    feature = earth_observation.xpath(
                        "om:featureOfInterest", namespaces=nsmap
                    )[0]
                    feature[0] = self.encode_footprint(
                        coverage.footprint.intersection(subset_polygon),
                        coverage.identifier
                    )
                except IndexError:
                    pass  # no featureOfInterest

        else:
            earth_observation = self.encode_earth_observation(
                coverage.identifier, coverage.begin_time, coverage.end_time,
                coverage.footprint, subset_polygon=subset_polygon
            )

        if not request:
            lineage = None

        elif request.method == "GET":
            lineage = EOWCS("lineage",
                EOWCS("referenceGetCoverage",
                    self.encode_reference("Reference",
                        request.build_absolute_uri().replace("&", "&amp;"),
                        False
                    )
                ), GML("timePosition", isoformat(now()))
            )
        elif request.method == "POST":  # TODO: better way to do this
            href = request.build_absolute_uri().replace("&", "&amp;")
            lineage = EOWCS("lineage",
                EOWCS("referenceGetCoverage",
                    OWS("ServiceReference",
                        OWS("RequestMessage",
                            etree.parse(request).getroot()
                        ), **{ns_xlink("href"): href}
                    )
                ), GML("timePosition", isoformat(now()))
            )

        return CIS("Metadata",
            EOWCS("EOMetadata",
                earth_observation,
                *[lineage] if lineage is not None else []
            )
        )

    def encode_coverage_description(self, coverage, srid=None, size=None,
                                    extent=None, footprint=None):
        source_mime = None
        for arraydata_location in coverage.arraydata_locations:
            if arraydata_location.format:
                source_mime = arraydata_location.format
                break

        native_format = None
        if source_mime:
            source_format = getFormatRegistry().getFormatByMIME(source_mime)
            # map the source format to the native one
            native_format = getFormatRegistry().mapSourceToNativeWCS21(
                source_format
            )
        # elif issubclass(coverage.real_type, RectifiedStitchedMosaic):
        #     # use the default format for RectifiedStitchedMosaics
        #     native_format = getFormatRegistry().getDefaultNativeFormat()
        # else:
        #     # TODO: improve if no native format availabe
        #     native_format = None
        sr = SpatialReference(4326)
        if extent:
            poly = Polygon.from_bbox(extent)
            poly.srid = srid
            extent = poly.transform(4326).extent

        else:
            # extent = coverage.extent
            extent = (0, 0, 1, 1)
            # sr = coverage.spatial_reference

        # if issubclass(coverage.real_type, ReferenceableDataset):
        #     rectified = False
        # else:
        #     rectified = True

        rectified = (not coverage.grid.is_referenceable)

        return WCS("CoverageDescription",
            self.encode_envelope(coverage, coverage.grid),
            self.encode_domain_set(coverage, srid, size, extent, rectified),
            self.encode_range_type(coverage.range_type),
            self.encode_eo_metadata(coverage),
            WCS("ServiceParameters",
                WCS("CoverageSubtype", self.get_coverage_subtype(coverage)),
                WCS(
                    "nativeFormat",
                    native_format.mimeType if native_format else ""
                )
            ),
            **{ns_gml("id"): self.get_gml_id(coverage.identifier)}
        )

    def encode_range_set(self, reference, mime_type):
        return GML("rangeSet",
            GML("File",
                GML("rangeParameters",
                    **{
                        ns_xlink("arcrole"): "fileReference",
                        ns_xlink("href"): reference,
                        ns_xlink("role"): mime_type
                    }
                ),
                GML("fileReference", reference),
                GML("fileStructure"),
                GML("mimeType", mime_type)
            )
        )

    def calculate_contribution(self, footprint, contributions,
                               subset_polygon=None):
        if subset_polygon:
            footprint = footprint.intersection(subset_polygon)

        for contribution in contributions:
            footprint = footprint.difference(contribution)
        contributions.append(footprint)
        return footprint

    def encode_contributing_datasets(self, coverage, subset_polygon=None):
        eo_objects = coverage.eo_objects
        if subset_polygon:
            if subset_polygon.srid != 4326:
                subset_polygon = subset_polygon.transform(4326, True)

            eo_objects = eo_objects.filter(
                footprint__intersects=subset_polygon
            )

        # iterate over all subsets in reverse order to get the
        eo_objects = eo_objects.order_by("-begin_time")
        actual_contributions = []
        all_contributions = []
        for eo_object in eo_objects:
            contribution = self.calculate_contribution(
                eo_object.footprint, all_contributions, subset_polygon
            )
            if not contribution.empty and contribution.num_geom > 0:
                actual_contributions.append((eo_object, contribution))

        return EOWCS("datasets", *[
            EOWCS("dataset",
                WCS("CoverageId", eo_object.identifier),
                EOWCS("contributingFootprint",
                    self.encode_footprint(
                        contrib, eo_object.identifier
                    )
                )
            )
            for eo_object, contrib in reversed(actual_contributions)
        ])

    def alter_rectified_dataset(self, coverage, request, tree,
                                subset_polygon=None):
        return EOWCS("RectifiedDataset", *(
            tree.getchildren() + [
                self.encode_eo_metadata(coverage, request, subset_polygon)
            ]
        ), **tree.attrib)

    def alter_rectified_stitched_mosaic(self, coverage, request, tree,
                                        subset_polygon=None):
        return EOWCS("RectifiedStitchedMosaic", *(
            tree.getchildren() + [
                self.encode_eo_metadata(coverage, request, subset_polygon),
                self.encode_contributing_datasets(coverage, subset_polygon)
            ]
        ), **tree.attrib)

    def encode_referenceable_dataset(self, coverage, range_type, reference,
                                     mime_type, subset=None):
        # handle subset
        dst_srid = coverage.srid

        if not subset:
            # whole area - no subset
            domain_set = self.encode_domain_set(coverage, rectified=False)
            eo_metadata = self.encode_eo_metadata(coverage)
            extent = coverage.extent
            sr = SpatialReference(dst_srid)

        else:
            # subset is given
            srid, size, extent, footprint = subset
            srid = srid if srid is not None else 4326

            domain_set = self.encode_domain_set(
                coverage, srid, size, extent, False
            )
            eo_metadata = self.encode_eo_metadata(
                coverage, subset_polygon=footprint
            )

            # get the WGS84 extent
            poly = Polygon.from_bbox(extent)
            poly.srid = srid
            if srid != dst_srid:
                poly.transform(dst_srid)
            extent = poly.extent
            sr = SpatialReference(srid)

        return EOWCS("ReferenceableDataset",
            self.encode_envelope(coverage, coverage.grid),
            domain_set,
            self.encode_range_set(reference, mime_type),
            self.encode_range_type(range_type),
            eo_metadata,
            **{
                ns_gml("id"): self.get_gml_id(coverage.identifier)
            }
        )

    def encode_dataset_series_description(self, dataset_series):
        elements = []
        if dataset_series.footprint:
            elements.append(
                self.encode_envelope(dataset_series, None)
            )

        elements.append(EOWCS("DatasetSeriesId", dataset_series.identifier))

        if dataset_series.begin_time and dataset_series.end_time:
            elements.append(
                self.encode_time_period(
                    dataset_series.begin_time, dataset_series.end_time,
                    "%s_timeperiod" % dataset_series.identifier
                )
            )

        return EOWCS("DatasetSeriesDescription",
            *elements,
            **{ns_gml("id"): self.get_gml_id(dataset_series.identifier)}
        )

    def encode_dataset_series_descriptions(self, dataset_series_set):
        return EOWCS("DatasetSeriesDescriptions", *[
            self.encode_dataset_series_description(dataset_series)
            for dataset_series in dataset_series_set
        ])

    def encode_eo_coverage_set_description(self, dataset_series_set, coverages,
                                           number_matched=None,
                                           number_returned=None):
        if number_matched is None:
            number_matched = len(coverages) + len(dataset_series_set)
        if number_returned is None:
            number_returned = len(coverages) + len(dataset_series_set)

        root = EOWCS("EOCoverageSetDescription",
            numberMatched=str(number_matched),
            numberReturned=str(number_returned)
        )

        if coverages:
            root.append(self.encode_coverage_descriptions(coverages))
        if dataset_series_set:
            root.append(self.encode_dataset_series_descriptions(
                dataset_series_set
            ))

        return root

    def get_schema_locations(self):
        return {ns_eowcs.uri: ns_eowcs.schema_location}