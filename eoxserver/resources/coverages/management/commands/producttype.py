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

from django.core.management.base import CommandError, BaseCommand
from django.db import transaction

from eoxserver.resources.coverages import models
from eoxserver.resources.coverages.management.commands import (
    CommandOutputMixIn, SubParserMixIn
)


class Command(CommandOutputMixIn, SubParserMixIn, BaseCommand):
    """ Command to manage product types. This command uses sub-commands for the
        specific tasks: create, delete
    """
    def add_arguments(self, parser):
        create_parser = self.add_subparser(parser, 'create')
        delete_parser = self.add_subparser(parser, 'delete')

        for parser in [create_parser, delete_parser]:
            parser.add_argument(
                'name', nargs=1, help='The product type name. Mandatory.'
            )

        create_parser.add_argument(
            '--mask-type', '-m', action='append', dest='mask_types', default=[],
            help=(
            )
        )
        create_parser.add_argument(
            '--browse-type', '-b', action='append', dest='browse_types', default=[],
            help=(
            )
        )

        delete_parser.add_argument(
            '--force', '-f', action='store_true', default=False,
            help='Also remove all products associated with that type.'
        )

    @transaction.atomic
    def handle(self, subcommand, name, *args, **kwargs):
        """ Dispatch sub-commands: create, delete.
        """
        name = name[0]
        if subcommand == "create":
            self.handle_create(name, *args, **kwargs)
        elif subcommand == "delete":
            self.handle_delete(name, *args, **kwargs)

    def handle_create(self, name, mask_types, browse_types, *args, **kwargs):
        """ Handle the creation of a new product type.
        """

        product_type = models.ProductType.objects.create(name=name)
        for mask_type_definition in mask_types:
            models.MaskType.objects.create(
                name=mask_type_definition, product_type=product_type
            )

    def handle_delete(self, name, force, **kwargs):
        """ Handle the deletion of a product type
        """

        try:
            product_type = models.ProductType.objects.get(name=name)
        except models.ProductType.DoesNotExist:
            raise CommandError('No such product type %r' % name)

        if force:
            products = models.Product.objects.filter(product_type=product_type)
            for product in products:
                product.delete()

        product_type.delete()

        # TODO: force