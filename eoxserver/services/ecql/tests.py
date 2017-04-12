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


from django.test import TransactionTestCase
from django.db.models import ForeignKey
from django.contrib.gis.geos import Polygon, MultiPolygon

from eoxserver.core.util.timetools import parse_iso8601
from eoxserver.resources.coverages import models
from eoxserver.services import ecql
from eoxserver.services.filters import get_field_mapping_for_model


class ECQLTestCase(TransactionTestCase):
    # mapping = {
    #     "identifier": "identifier",
    #     "id": "identifier",
    #     "beginTime": "begin_time",
    #     "endTime": "end_time",
    #     "footprint": "footprint",
    #     "parentIdentifier": "metadata__parent_identifier",
    #     "illuminationAzimuthAngle": "metadata__illumination_azimuth_angle",
    #     "illuminationZenithAngle": "metadata__illumination_zenith_angle",
    #     "illuminationElevationAngle": "metadata__illumination_elevation_angle"
    # }

    def setUp(self):
        p = parse_iso8601
        range_type = models.RangeType.objects.create(name="RGB")
        # models.RectifiedDataset.objects.create(
        #     identifier="A",
        #     footprint=MultiPolygon(Polygon.from_bbox((0, 0, 5, 5))),
        #     begin_time=p("2000-01-01T00:00:00Z"),
        #     end_time=p("2000-01-01T00:00:05Z"),
        #     srid=4326, min_x=0, min_y=0, max_x=5, max_y=5,
        #     size_x=100, size_y=100,
        #     range_type=range_type
        # )

        self.create(dict(
            identifier="A",
            footprint=MultiPolygon(Polygon.from_bbox((0, 0, 5, 5))),
            begin_time=p("2000-01-01T00:00:00Z"),
            end_time=p("2000-01-01T00:00:05Z"),
            srid=4326, min_x=0, min_y=0, max_x=5, max_y=5,
            size_x=100, size_y=100,
            range_type=range_type
        ), dict(
            illumination_azimuth_angle=10.0,
            illumination_zenith_angle=20.0,
            illumination_elevation_angle=30.0,
        ), dict(
            parent_identifier="AparentA",
            orbit_number="AAA",
            orbit_direction="ASCENDING"
        ))

        self.create(dict(
            identifier="B",
            footprint=MultiPolygon(Polygon.from_bbox((5, 5, 10, 10))),
            begin_time=p("2000-01-01T00:00:05Z"),
            end_time=p("2000-01-01T00:00:10Z"),
            srid=4326, min_x=5, min_y=5, max_x=10, max_y=10,
            size_x=100, size_y=100,
            range_type=range_type
        ), dict(
            illumination_azimuth_angle=20.0,
            illumination_zenith_angle=30.0,
        ), dict(
            parent_identifier="BparentB",
            orbit_number="BBB",
            orbit_direction="DESCENDING"
        ))

    def create_metadata(self, coverage, metadata, product_metadata):
        def is_common_value(field):
            try:
                if isinstance(field, ForeignKey):
                    field.related.parent_model._meta.get_field('value')
                    return True
            except:
                pass
            return False

        def convert(name, value, model_class):
            field = model_class._meta.get_field(name)
            if is_common_value(field):
                return field.related.parent_model.objects.get_or_create(
                    value=value
                )[0]
            elif field.choices:
                return dict((v, k) for k, v in field.choices)[value]
            return value

        pm = models.ProductMetadata.objects.create(**dict(
            (name, convert(name, value, models.ProductMetadata))
            for name, value in product_metadata.items()
        ))
        return models.CoverageMetadata.objects.create(
            coverage=coverage, product_metadata=pm, **dict(
                (name, convert(name, value, models.CoverageMetadata))
                for name, value in metadata.items()
            )
        )

    def create(self, coverage_params, metadata, product_metadata):
        c = models.RectifiedDataset.objects.create(**coverage_params)
        self.create_metadata(c, metadata, product_metadata)
        return c

    def create_collection(self, collection_params, metadata):
        pass

    def create_opt(self, coverage_params, metadata):
        pass

    def create_sar(self, coverage_params, metadata):
        pass

    def evaluate(self, cql_expr, expected_ids, model_type=None):
        model_type = model_type or models.RectifiedDataset
        mapping, mapping_choices = get_field_mapping_for_model(model_type)

        ast = ecql.parse(cql_expr)

        # print
        # print
        # print cql_expr
        # #print ecql.get_repr(ast)
        filters = ecql.to_filter(ast, mapping, mapping_choices)
        # print filters

        qs = model_type.objects.filter(filters)

        self.assertItemsEqual(
            expected_ids, qs.values_list("identifier", flat=True)
        )

    # common comparisons

    def test_id_eq(self):
        self.evaluate(
            'identifier = "A"',
            ('A',)
        )

    def test_id_ne(self):
        self.evaluate(
            'identifier <> "B"',
            ('A',)
        )

    def test_float_lt(self):
        self.evaluate(
            'illuminationZenithAngle < 30',
            ('A',)
        )

    def test_float_le(self):
        self.evaluate(
            'illuminationZenithAngle <= 20',
            ('A',)
        )

    def test_float_gt(self):
        self.evaluate(
            'illuminationZenithAngle > 20',
            ('B',)
        )

    def test_float_ge(self):
        self.evaluate(
            'illuminationZenithAngle >= 30',
            ('B',)
        )

    def test_float_between(self):
        self.evaluate(
            'illuminationZenithAngle BETWEEN 19 AND 21',
            ('A',)
        )

    # test different field types

    def test_common_value_eq(self):
        self.evaluate(
            'orbitNumber = "AAA"',
            ('A',)
        )

    def test_common_value_in(self):
        self.evaluate(
            'orbitNumber IN ("AAA", "XXX")',
            ('A',)
        )

    def test_common_value_like(self):
        self.evaluate(
            'orbitNumber LIKE "AA%"',
            ('A',)
        )

    def test_common_value_like_middle(self):
        self.evaluate(
            r'orbitNumber LIKE "A%A"',
            ('A',)
        )

    def test_enum_value_eq(self):
        self.evaluate(
            'orbitDirection = "ASCENDING"',
            ('A',)
        )

    def test_enum_value_in(self):
        self.evaluate(
            'orbitDirection IN ("ASCENDING")',
            ('A',)
        )

    def test_enum_value_like(self):
        self.evaluate(
            'orbitDirection LIKE "ASCEN%"',
            ('A',)
        )

    def test_enum_value_ilike(self):
        self.evaluate(
            'orbitDirection ILIKE "ascen%"',
            ('A',)
        )

    def test_enum_value_ilike_start_middle_end(self):
        self.evaluate(
            r'orbitDirection ILIKE "a%en%ing"',
            ('A',)
        )

    # (NOT) LIKE | ILIKE

    def test_like_beginswith(self):
        self.evaluate(
            'parentIdentifier LIKE "A%"',
            ('A',)
        )

    def test_ilike_beginswith(self):
        self.evaluate(
            'parentIdentifier ILIKE "a%"',
            ('A',)
        )

    def test_like_endswith(self):
        self.evaluate(
            r'parentIdentifier LIKE "%A"',
            ('A',)
        )

    def test_ilike_endswith(self):
        self.evaluate(
            r'parentIdentifier ILIKE "%a"',
            ('A',)
        )

    def test_like_middle(self):
        self.evaluate(
            r'parentIdentifier LIKE "%parent%"',
            ('A', 'B')
        )

    def test_like_startswith_middle(self):
        self.evaluate(
            r'parentIdentifier LIKE "A%rent%"',
            ('A',)
        )

    def test_like_middle_endswith(self):
        self.evaluate(
            r'parentIdentifier LIKE "%ren%A"',
            ('A',)
        )

    def test_like_startswith_middle_endswith(self):
        self.evaluate(
            r'parentIdentifier LIKE "A%ren%A"',
            ('A',)
        )

    def test_ilike_middle(self):
        self.evaluate(
            'parentIdentifier ILIKE "%PaReNT%"',
            ('A', 'B')
        )

    def test_not_like_beginswith(self):
        self.evaluate(
            'parentIdentifier NOT LIKE "B%"',
            ('A',)
        )

    def test_not_ilike_beginswith(self):
        self.evaluate(
            'parentIdentifier NOT ILIKE "b%"',
            ('A',)
        )

    def test_not_like_endswith(self):
        self.evaluate(
            r'parentIdentifier NOT LIKE "%B"',
            ('A',)
        )

    def test_not_ilike_endswith(self):
        self.evaluate(
            r'parentIdentifier NOT ILIKE "%b"',
            ('A',)
        )

    # (NOT) IN

    def test_string_in(self):
        self.evaluate(
            'identifier IN ("A", \'B\')',
            ('A', 'B')
        )

    def test_string_not_in(self):
        self.evaluate(
            'identifier NOT IN ("B", \'C\')',
            ('A',)
        )

    # (NOT) NULL

    def test_string_null(self):
        self.evaluate(
            'illuminationElevationAngle IS NULL',
            ('B',)
        )

    def test_string_not_null(self):
        self.evaluate(
            'illuminationElevationAngle IS NOT NULL',
            ('A',)
        )

    # temporal predicates

    def test_before(self):
        self.evaluate(
            'beginTime BEFORE 2000-01-01T00:00:01Z',
            ('A',)
        )

    def test_before_or_during_dt_dt(self):
        self.evaluate(
            'beginTime BEFORE OR DURING '
            '2000-01-01T00:00:00Z / 2000-01-01T00:00:01Z',
            ('A',)
        )

    def test_before_or_during_dt_td(self):
        self.evaluate(
            'beginTime BEFORE OR DURING '
            '2000-01-01T00:00:00Z / PT4S',
            ('A',)
        )

    def test_before_or_during_td_dt(self):
        self.evaluate(
            'beginTime BEFORE OR DURING '
            'PT4S / 2000-01-01T00:00:03Z',
            ('A',)
        )

    def test_during_td_dt(self):
        self.evaluate(
            'beginTime BEFORE OR DURING '
            'PT4S / 2000-01-01T00:00:03Z',
            ('A',)
        )

    # TODO: test DURING OR AFTER / AFTER

    # spatial predicates

    def test_intersects_point(self):
        self.evaluate(
            'INTERSECTS(footprint, POINT(1 1.0))',
            ('A',)
        )

    def test_intersects_mulitipoint_1(self):
        self.evaluate(
            'INTERSECTS(footprint, MULTIPOINT(0 0, 1 1))',
            ('A',)
        )

    def test_intersects_mulitipoint_2(self):
        self.evaluate(
            'INTERSECTS(footprint, MULTIPOINT((0 0), (1 1)))',
            ('A',)
        )

    def test_intersects_linestring(self):
        self.evaluate(
            'INTERSECTS(footprint, LINESTRING(0 0, 1 1))',
            ('A',)
        )

    def test_intersects_multilinestring(self):
        self.evaluate(
            'INTERSECTS(footprint, MULTILINESTRING((0 0, 1 1), (2 1, 1 2)))',
            ('A',)
        )

    def test_intersects_polygon(self):
        self.evaluate(
            'INTERSECTS(footprint, '
            'POLYGON((0 0, 3 0, 3 3, 0 3, 0 0), (1 1, 2 1, 2 2, 1 2, 1 1)))',
            ('A',)
        )

    def test_intersects_multipolygon(self):
        self.evaluate(
            'INTERSECTS(footprint, '
            'MULTIPOLYGON(((0 0, 3 0, 3 3, 0 3, 0 0), '
            '(1 1, 2 1, 2 2, 1 2, 1 1))))',
            ('A',)
        )

    def test_intersects_envelope(self):
        self.evaluate(
            'INTERSECTS(footprint, ENVELOPE(0 0 1.0 1.0))',
            ('A',)
        )

    def test_dwithin(self):
        self.evaluate(
            'DWITHIN(footprint, POINT(0 0), 10, meters)',
            ('A',)
        )

    def test_bbox(self):
        self.evaluate(
            'BBOX(footprint, 0, 0, 1, 1, "EPSG:4326")',
            ('A',)
        )

    # TODO: other relation methods

    # arithmethic expressions

    def test_arith_simple_plus(self):
        self.evaluate(
            'illuminationZenithAngle = 10 + 10',
            ('A',)
        )

    def test_arith_field_plus_1(self):
        self.evaluate(
            'illuminationZenithAngle = illuminationAzimuthAngle + 10',
            ('A', 'B')
        )

    def test_arith_field_plus_2(self):
        self.evaluate(
            'illuminationZenithAngle = 10 + illuminationAzimuthAngle',
            ('A', 'B')
        )

    def test_arith_field_plus_field(self):
        self.evaluate(
            'illuminationElevationAngle = '
            'illuminationZenithAngle + illuminationAzimuthAngle',
            ('A',)
        )

    def test_arith_field_plus_mul_1(self):
        self.evaluate(
            'illuminationZenithAngle = illuminationAzimuthAngle * 1.5 + 5',
            ('A',)
        )

    def test_arith_field_plus_mul_2(self):
        self.evaluate(
            'illuminationZenithAngle = 5 + illuminationAzimuthAngle * 1.5',
            ('A',)
        )
