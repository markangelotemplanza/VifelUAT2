# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging
from datetime import datetime, timedelta
import re
from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.osv.expression import AND, OR

_logger = logging.getLogger(__name__)

class multiple_relocation(models.TransientModel):
    _inherit = 'stock.quant.relocate'
    
    def action_relocate_quants(self):
        self.ensure_one()
        relocation_form_series = self.env['ir.sequence'].search([('code', '=', 'relocate.form.series')], limit=1)
        x_reloc_batch_number = relocation_form_series.next_by_id()

        for quant in self.quant_ids:
            if quant.x_studio_special_holding:
                raise UserError('\nYou cannot relocate pallets that are on Special Holding State')
            if quant.available_quantity != quant.quantity:
                raise UserError(f"\nRecord with a Product of {quant.product_id.display_name} and a Pallet of {quant.package_id.name} seems to have quantites reserved on a picking record. Please release them before relocating the stock record.")
        # Group quants by package_id and location_id
        grouped_quants = {}
        for quant in self.quant_ids:
            key = (quant.package_id.id, quant.location_id.id)
            if key not in grouped_quants:
                grouped_quants[key] = self.env['stock.quant']
            grouped_quants[key] |= quant
    
        for (package_id, location_id), quants in grouped_quants.items():
            dest_location_id = quants[0].x_studio_dest_relocation
            if dest_location_id:
                # Perform relocation actions for the group of quants
                if self.is_partial_package and not self.dest_package_id:
                    quants_to_unpack = quants.filtered(lambda q: not all(sub_q in quants.ids for sub_q in q.package_id.quant_ids.ids))
                    quants_to_unpack.move_quants(location_dest_id=dest_location_id, message=self.message, unpack=True)
                    quants -= quants_to_unpack
    
                quants.move_quants(
                    location_dest_id=dest_location_id,
                    package_dest_id=self.dest_package_id,
                    message=self.message,
                    x_studio_warehouseman=self.x_studio_warehouseman,
                    x_reloc_batch_number=x_reloc_batch_number
                )
    
        # Handle lot and product actions
        lot_ids = self.quant_ids.mapped('lot_id')
        product_ids = self.quant_ids.mapped('product_id')
    
        if self.env.context.get('default_lot_id', False) and len(lot_ids) == 1:
            lot_ids.action_lot_open_quants()
        elif self.env.context.get('single_product', False) and len(product_ids) == 1:
            product_ids.action_update_quantity_on_hand()




class stock_move_line_Override(models.Model):
    _inherit = 'stock.move.line'
    # Disable me then enable if adding field in stock.move.line model
    # result_package_id = fields.Many2one(
    #     'stock.quant.package', 'Destination Package',
    #     ondelete='restrict', required=False, check_company=True,
    #     domain="['|', '|', '&', ('location_id', '=', False), ('location_id', '=', location_dest_id), ('id', '=', package_id), '|', ('owner_id', '=', owner_id), ('owner_id', '=', False)]",
    #     help="If set, the operations are packed into this package")


    
    def sort_by_batch(self):
        sorted_docs = sorted(self, key=lambda line: (line.x_relocate_batch, line.owner_id.name))
        return sorted_docs
    
    @api.onchange('x_studio_expiration_date')
    def _onchange_expiry_date(self):
        expiry_date_range = self.env['product.product'].search([('id', '=', self.product_id.id)])
        product_brand_expiry = expiry_date_range.x_studio_client_expiry_range.mapped('x_studio_brand_name.name')

        warning = None

        for line in expiry_date_range.x_studio_client_expiry_range:
            if line.x_studio_client_1 == self.owner_id:
                today = fields.Date.today()
                not_acceptable = today + timedelta(days=line.x_studio_expiry_date_range.x_studio_float_value)
                
                if (self.x_studio_expiration_date < not_acceptable and self.product_id.product_template_variant_value_ids.name in product_brand_expiry):
                    self.x_studio_exp_warned = True
                    warning = {
                        'title': "Expiration Threshold Warning!",
                        'message': (
                            f"\nExpiration date is outside the acceptable expiration date range. "
                            f"Please review the Product.\n\n"
                            f"Entered Expiration Date: {datetime.strptime(str(self.x_studio_expiration_date), '%Y-%m-%d').strftime('%B %d, %Y')}\n"
                            f"Acceptable Expiration Date Range: {datetime.strptime(str(not_acceptable), '%Y-%m-%d').strftime('%B %d, %Y')}"
                        ),
                    }
                    break
                else:
                    self.x_studio_exp_warned = False
        if warning:
            return {'warning': warning}
    
    @api.depends('move_id', 'move_id.location_id', 'move_id.location_dest_id', 'result_package_id')
    def _compute_location_id(self):
        for line in self:
            if not line.location_id:
                line.location_id = line.move_id.location_id or line.picking_id.location_id
            if not line.location_dest_id:
                line.location_dest_id = line.move_id.location_dest_id or line.picking_id.location_dest_id
            if line.result_package_id.location_id:
                line.location_dest_id = line.result_package_id.location_id

    


class ensure_ownership(models.Model):
    _inherit = 'stock.move'
    
    def _update_reserved_quantity(self, need, location_id, quant_ids=None, lot_id=None, package_id=None, owner_id=None, strict=True):
        """ Create or update move lines and reserves quantity from quants
            Expects the need (qty to reserve) and location_id to reserve from.
            `quant_ids` can be passed as an optimization since no search on the database
            is performed and reservation is done on the passed quants set
        """

        
        self.ensure_one()
        if quant_ids is None:
            quant_ids = self.env['stock.quant']
        if not lot_id:
            lot_id = self.env['stock.lot']
        if not package_id:
            package_id = self.env['stock.quant.package']
        if not owner_id:
            owner_id = self.env['res.partner']


        
        
        quants = quant_ids._get_reserve_quantity(
            self.product_id, location_id, need, product_packaging_id=self.product_packaging_id,
            uom_id=self.product_uom, lot_id=lot_id, package_id=package_id, owner_id=self.partner_id, strict=strict)

        # _logger.info(self)
        taken_quantity = 0
        rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        # Find a candidate move line to update or create a new one.
        
        for reserved_quant, quantity, in quants:
            
            taken_quantity += quantity
            to_update = next((line for line in self.move_line_ids if line._reservation_is_updatable(quantity, reserved_quant)), False)
            if to_update:
                uom_quantity = self.product_id.uom_id._compute_quantity(quantity, to_update.product_uom_id, rounding_method='HALF-UP')
                uom_quantity = float_round(uom_quantity, precision_digits=rounding)
                uom_quantity_back_to_product_uom = to_update.product_uom_id._compute_quantity(uom_quantity, self.product_id.uom_id, rounding_method='HALF-UP')
            if to_update and float_compare(quantity, uom_quantity_back_to_product_uom, precision_digits=rounding) == 0:
                to_update.with_context(reserved_quant=reserved_quant).quantity += uom_quantity
            else:
                if self.product_id.tracking == 'serial':
                    vals_list = self._add_serial_move_line_to_vals_list(reserved_quant, quantity)
                    if vals_list:
                        self.env['stock.move.line'].with_context(reserved_quant=reserved_quant).create(vals_list)
                else:
                    self.env['stock.move.line'].with_context(reserved_quant=reserved_quant).create(self._prepare_move_line_vals(quantity=quantity, reserved_quant=reserved_quant))

        return taken_quantity




class override_stock_quant(models.Model):
    _inherit = 'stock.quant'
    x_studio_special_holding = fields.Boolean()

    

    @api.onchange('x_studio_dest_relocation')
    def _onchange_destination_relocation(self):
        if self.x_studio_dest_relocation:
            # Combined search to minimize database queries
            quant_records = self.env['stock.quant'].search([
                '|',
                ('x_studio_dest_relocation.id', '=', self.x_studio_dest_relocation.id),
                ('package_id.id', '=', self.package_id.id)
            ], order='x_studio_dest_relocation')
    
            # Use sets to check for duplicates and inconsistencies
            relocation_ids = set()
            package_ids = set()
            first_init_loc = None
    
            for quant in quant_records:
                if quant.x_studio_dest_relocation.id == self.x_studio_dest_relocation.id:
                    if quant.package_id.id != self.package_id.id:
                        raise UserError("It seems like the last location you've selected is already chosen as another relocation location. Please change the location.")
                if quant.package_id.id == self.package_id.id:
                    first_init_loc = quant.x_studio_dest_relocation
                    if first_init_loc != self.x_studio_dest_relocation and first_init_loc:
                        raise UserError("You cannot move the same Pallet into multiple Locations.")
    
            # Note: No need for additional loops or checks since all conditions are handled within the single loop
                    


    
    # def _gather(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False, qty=0):
    #     """ if records in self, the records are filtered based on the wanted characteristics passed to this function
    #         if not, a search is done with all the characteristics passed.
    #     """
    #     removal_strategy = self._get_removal_strategy(product_id, location_id)
    #     domain = self._get_gather_domain(product_id, location_id, lot_id, package_id, owner_id, strict)
    #     domain, order = self._get_removal_strategy_domain_order(domain, removal_strategy, qty)
        
    #     if self.ids:
    #         sort_key = self._get_removal_strategy_sort_key(removal_strategy)
    #         res = self.filtered_domain(domain).sorted(key=sort_key[0], reverse=sort_key[1])
    #     else:
    #         res = self.search(domain, order=order)
    #     # List to store all matching stock.quant records
    #     #TODO: Try adding also closest to expiration
    #     if removal_strategy == "closest":
    #         res = res.sorted(lambda q: (q.location_id.complete_name, -q.id))
            
    #     temp_var = self.env['stock.quant'].browse()
    #     # raise UserError(len(self.env.user.groups_id))
    #     for x in res:
    #         # Search for stock.quant records matching x.id
    #         quants = self.env['stock.quant'].search([('id', '=', x.id)])
    #         # _logger.info(dir(quants))
            
    #         # if not quants.x_studio_special_holding and quants.x_studio_reference:
    #         if not quants.x_studio_special_holding:
    #         # if not quants.x_studio_special_holding:
    #             # _logger.info(quants.x_studio_reference)
    #             temp_var += quants
            
    #     return temp_var

    def _gather(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False, qty=0):
        """ if records in self, the records are filtered based on the wanted characteristics passed to this function
            if not, a search is done with all the characteristics passed.
        """
        removal_strategy = self._get_removal_strategy(product_id, location_id)
        domain = self._get_gather_domain(product_id, location_id, lot_id, package_id, owner_id, strict)
        domain, order = self._get_removal_strategy_domain_order(domain, removal_strategy, qty)

        quants_cache = self.env.context.get('quants_cache')
        if quants_cache is not None and strict and removal_strategy != 'least_packages':
            res = self.env['stock.quant']
            if lot_id:
                res |= quants_cache[product_id.id, location_id.id, lot_id.id, package_id.id, owner_id.id]
            res |= quants_cache[product_id.id, location_id.id, False, package_id.id, owner_id.id]
        else:
            res = self.search(domain, order=order)
        if removal_strategy == "closest":
            res = res.sorted(lambda q: (q.location_id.complete_name, -q.id))

        
        return res.sorted(key=lambda q: (q.x_studio_special_holding, not q.lot_id))

    
    # Add Total to available_quantity and inventory_quantity_auto_apply columns on Group By
    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        # Call the parent method and get the result
        res = super(override_stock_quant, self).read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
        
        # Check if 'available_quantity' or 'inventory_quantity_auto_apply' is in the fields list
        if 'available_quantity' in fields or 'inventory_quantity_auto_apply' in fields:
            for line in res:
                if '__domain' in line:
                    lines = self.search(line['__domain'])
                    
                    # Compute the total for available_quantity if it is in fields
                    if 'available_quantity' in fields:
                        total_available_quantity = sum(record.available_quantity for record in lines)
                        line['available_quantity'] = total_available_quantity

                    # Compute the total for inventory_quantity_auto_apply if it is in fields
                    if 'inventory_quantity_auto_apply' in fields:
                        total_inventory_quantity_auto_apply = sum(record.inventory_quantity_auto_apply for record in lines)
                        line['inventory_quantity_auto_apply'] = total_inventory_quantity_auto_apply
        
        return res



    def _get_inventory_move_values(self, qty, location_id, location_dest_id, package_id=False, package_dest_id=False, x_studio_warehouseman=False, x_reloc_batch_number=False):
        """ Called when user manually set a new quantity (via `inventory_quantity`)
        just before creating the corresponding stock move.

        :param location_id: `stock.location`
        :param location_dest_id: `stock.location`
        :param package_id: `stock.quant.package`
        :param package_dest_id: `stock.quant.package`
        :return: dict with all values needed to create a new `stock.move` with its move line.
        """
        self.ensure_one()
        if self.env.context.get('inventory_name'):
            name = self.env.context.get('inventory_name')
        elif fields.Float.is_zero(qty, 0, precision_rounding=self.product_uom_id.rounding):
            name = _('Product Quantity Confirmed')
        else:
            name = _('Product Quantity Updated')
        if self.user_id and self.user_id.id != SUPERUSER_ID:
            name += f' ({self.user_id.display_name})'

        return {
            'name': name,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom_id.id,
            'product_uom_qty': qty,
            'company_id': self.company_id.id or self.env.company.id,
            'state': 'confirmed',
            'location_id': location_id.id,
            'location_dest_id': location_dest_id.id,
            'restrict_partner_id':  self.owner_id.id,
            'is_inventory': True,
            'picked': True,
            'move_line_ids': [(0, 0, {
                'product_id': self.product_id.id,
                'product_uom_id': self.product_uom_id.id,
                'quantity': qty,
                'location_id': location_id.id,
                'location_dest_id': location_dest_id.id,
                'company_id': self.company_id.id or self.env.company.id,
                'lot_id': self.lot_id.id,
                'package_id': package_id.id if package_id else False,
                'result_package_id': package_dest_id.id if package_dest_id else False,
                'owner_id': self.owner_id.id,
                'x_studio_warehouseman': x_studio_warehouseman,
                'x_relocate_batch': x_reloc_batch_number
            })]
        }


    def move_quants(self, location_dest_id=False, package_dest_id=False, message=False, unpack=False, x_studio_warehouseman=False, x_reloc_batch_number=False):
        """ Directly move a stock.quant to another location and/or package by creating a stock.move.

        :param location_dest_id: `stock.location` destination location for the quants
        :param package_dest_id: `stock.quant.package´ destination package for the quants
        :param message: String to fill the reference field on the generated stock.move
        :param unpack: set to True when needing to unpack the quant
        """
        message = message or _('Quantity Relocated')
        move_vals = []
        for quant in self:
            result_package_id = package_dest_id  # temp variable to keep package_dest_id unchanged
            if not unpack and not package_dest_id:
                result_package_id = quant.package_id
            move_vals.append(quant.with_context(inventory_name=message)._get_inventory_move_values(
                quant.quantity,
                quant.location_id,
                location_dest_id or quant.location_id,
                quant.package_id,
                result_package_id,
                x_studio_warehouseman,
                x_reloc_batch_number
            ))
        moves = self.env['stock.move'].create(move_vals)
        moves._action_done()
        
class transfer_locations(models.Model):
    _inherit = 'stock.picking'


    location_id = fields.Many2one(
        'stock.location', "Source Location",
         store=True,  readonly=False,
        check_company=True, required=True, domain="[('id', 'in', allowed_value_ids)]")


    location_dest_id = fields.Many2one(
        'stock.location', "Destination Location",
       store=True,  readonly=False,
        check_company=True, required=True, domain="[('id', 'in', allowed_value_ids)]")


    
    allowed_value_ids = fields.Many2many(
        'stock.location', compute="_compute_allowed_value_ids", string="Allowed Locations", store=True
    )

    gentle_reminder = fields.Char(string="Reminder")
        
    def action_return_packages(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Return Packages',
            'res_model': 'return.package.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('multiple_relocation.view_return_package_wizard_form').id,
            'target': 'new',  # 'new' opens in a modal popup, 'self' opens in the same window
            'context': {
                'default_picking_id': self.id,  # Pass the current picking_id to the wizard
            },
        }

    def multiple_products_in_one_pallet(self):    
        locs_and_pallets_expiration = []
        move_lines = self.move_line_ids
        conflicting_pallets = {}  # To store conflicting products for each pallet
    
        for line in move_lines:
            location, package = line.location_dest_id, line.result_package_id
    
            # Check if the package (pallet) is already in our tracker
            for data in locs_and_pallets_expiration:
                if data['package_id'] == line.result_package_id.id and data['product_id'] != line.product_id.id:
                    # Store the conflicting products in a dictionary with pallet id as key
                    if line.result_package_id.name not in conflicting_pallets:
                        conflicting_pallets[line.result_package_id.name] = [data['display_name']]
                    
                    # Add the current product to the conflict list if it's not already added
                    if line.product_id.display_name not in conflicting_pallets[line.result_package_id.name]:
                        conflicting_pallets[line.result_package_id.name].append(line.product_id.display_name)
            
            # Track the current line's package and product details
            locs_and_pallets_expiration.append({
                'location_id': location.id,
                'package_id': package.id,
                'product_id': line.product_id.id,
                'display_name': line.product_id.display_name,
                'x_studio_production_date': line.x_studio_production_date,
                'x_studio_expiration_date': line.x_studio_expiration_date,
                'x_studio_container_number': line.x_studio_container_number,
            })
    
        # If any conflicting pallets are found, raise an error
        if conflicting_pallets:
            conflict_messages = []
            for pallet, products in conflicting_pallets.items():
                product_list = ", ".join(products)
                conflict_messages.append(f"• Pallet: '{pallet}' contains multiple products: {product_list}")
            
            # Use \n to create line breaks
            self.gentle_reminder = "Reminder:\n" + "\n".join(conflict_messages) + "\n\nAre you sure you want to insert each line of multiple products into a single pallet?"
        else:
            self.gentle_reminder = ""

  



            
         
    
    @api.depends('x_studio_is_a_blast_freezer', 'partner_id', 'x_studio_warehouse_sh')
    def _compute_allowed_value_ids(self):
        for record in self:
            if record.state == 'done' or not record.partner_id:
                record.allowed_value_ids = []
                continue
            if record.picking_type_code == 'outgoing':
                if record.x_studio_is_a_blast_freezer:
                    locations_with_partner_quants = self.env['stock.quant'].search([
                        ('owner_id', '=', record.partner_id.id),
                        ('location_id.x_studio_is_a_blast_freezer', '=', True)
                    ]).mapped('location_id.id')
                    
                    record.allowed_value_ids = self.env['stock.location'].browse(locations_with_partner_quants)
                else:
                    allowed_locations = self.env["stock.location"].search([
                        "&", 
                        "|", 
                        ("child_ids.child_ids.child_ids.x_studio_occupied_by", "=", record.partner_id.id),
                        ("child_ids.child_ids.x_studio_occupied_by", "=", record.partner_id.id),
                        ("warehouse_id.code", "=", record.x_studio_warehouse_sh)
                    ])
                    record.allowed_value_ids = allowed_locations

            elif record.picking_type_code == 'incoming':
                if record.x_studio_is_a_blast_freezer:
                    record.allowed_value_ids = self.env['stock.location'].search([('x_studio_is_a_blast_freezer', '=', True)])
                else:
                    record.allowed_value_ids = self.env['stock.location'].search([
                        '&',
                        ('child_ids.child_ids', '!=', False),
                        ('name', '!=', 'Stock'),
                        ('warehouse_id.code', '=', record.x_studio_warehouse_sh),
                        ('location_id', '!=', False),
                        ('name', 'not ilike', "BF")
                    ])
            else:
                record.allowed_value_ids = []

    def has_generated_an_ncr(self):
        self.x_studio_has_generated_an_ncr = True
        return 
    # Call on Adjustment Report Remarks
    
    # @api.onchange('x_studio_hidden_field')
    def GetRemarks(self):
        Remarks = []
        # raise UserError(Remarks)
        for msg in self.message_ids:
            if msg.body and msg.mail_activity_type_id.name == "Request for Revision":
                div_match = re.search(r'<div>(.*?)</div>', msg.body, re.DOTALL)
                div_count = len(re.findall(r'<div>', msg.body))
                if div_match and div_count > 1:
                    div_content = div_match.group(1)
                    # Check if div_content contains o_mail_note_title
                    if 'o_mail_note_title' not in div_content:
                        cleaned_content = re.sub(r'<br\s*/?>', '\n', div_content)  # Replace <br> tags with newlines
                        cleaned_content = re.sub(r'\s*\n\s*', '\n', cleaned_content).strip()  # Remove extra whitespace around newlines
                        Remarks.append(cleaned_content)
                elif div_count == 1:
                    Remarks.append("----")
        
        return Remarks

    # This doesnt include the product and quantity modification
    # @api.onchange('x_studio_hidden_field')
    def AuditTrail(self):
        Values = []
        # TODO: ONCLICK pull a sequence for adjustment form numbered series then set it in field x_studio_set_adjustment_series
        # then use that in report, if x_studio_set_adjustment_series is already set then don't increment.

        # raise UserError(self.message_ids)
        # Filter messages where tracking_value_ids exists and field name contains 'x_studio'
        filtered_messages = [
            msg for msg in self.message_ids
            if msg.tracking_value_ids
            and any(
                hasattr(tracking_value, 'field_id')
                and isinstance(tracking_value.field_id.name, str)
                and 'x_studio' in tracking_value.field_id.name
                and any(
                    getattr(tracking_value, field)
                    for field in ['old_value_text', 'old_value_integer', 'old_value_float', 'old_value_datetime', 'old_value_char']
                )
                for tracking_value in msg.tracking_value_ids
            )
        ]
        # Define fields in priority order
        fields = ['old_value_text', 'old_value_integer', 'old_value_float', 'old_value_datetime', 'old_value_char']
        new_fields = ['new_value_text', 'new_value_integer', 'new_value_float', 'new_value_datetime', 'new_value_char']
        
        # Retrieve the value with old value
        for msg in filtered_messages:
            message_values = {}
            for field, new_field in zip(fields, new_fields):
                old_value = getattr(msg.tracking_value_ids, field)
                
                new_value = getattr(msg.tracking_value_ids, new_field)
                if old_value or new_value:
                    Values.insert(0, {
                        'field': msg.tracking_value_ids.field_id.field_description,
                        'old_value': old_value,
                        'new_value': new_value if new_value else None
                    })
        
        if not self.x_studio_set_adjustment_series:
            adjustment_form_series = self.env['ir.sequence'].search([('code', '=', 'adjustment.form.series')], limit=1)
            
            if not adjustment_form_series:
                raise UserError("Adjustment Form Series sequence not found.")
            
            # Get and increment the next number in the sequence
            next_number = adjustment_form_series.next_by_id()
            
            # Set the field to the next number in the sequence
            self.x_studio_set_adjustment_series = next_number
    
        return Values

#TODO: Add a Source document field, for last document -Fixed
#TODO: Add Client Ref for move.lines - Fixed
#TODO: re-write details on relocated relocations - Fixed
#TODO: Fix copy - Fixed
#TODO: Change Reference to many2one instead of text - For Testing
#ADDED: AUTOMATIC GENERATION OF LINES