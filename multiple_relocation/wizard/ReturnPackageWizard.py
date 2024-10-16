from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class ReturnPackageWizardLine(models.TransientModel):
    _name = 'return.package.wizard.line'
    _description = 'Line for Returning Packages'

    wizard_id = fields.Many2one('return.package.wizard', string="Wizard")
    select_package = fields.Boolean(string="Select")
    result_package_id = fields.Many2one('stock.quant.package', string="Package")
    pallet_series_id = fields.Char(string='Pallet Series ID')
    product_id = fields.Many2one('product.product', string="Products")
    quantity = fields.Float(string="Quantity")
    production_date=fields.Date(string="Production Date")
    expiration_date=fields.Date(string="Expiration Date")
    container_number = fields.Char(string="Container #")
    return_counter = fields.Integer(string="No. of Returns")
    stock_move_line = fields.Integer(string="Move Line ID")
    pack_uom_unit = fields.Float(string="Packaging Unit")
    min_uom_unit = fields.Float(string="Min Unit")
    location_dest_id = fields.Many2one('stock.location', string="Destination Location")
    pack_uom = fields.Many2one('uom.uom', string='Unit of Measure')
    min_uom = fields.Many2one('uom.uom', string='Unit of Measure')
    actual_quantity = fields.Float(string="Actual Quantity")
    actual_pack_uom_unit = fields.Float(string="Packaging Unit")
    actual_min_uom_unit = fields.Float(string="Min Unit")
    
class ReturnPackageWizard(models.TransientModel):
    _name = 'return.package.wizard'
    _description = 'Wizard for Returning Packages'

    package_line_ids = fields.One2many(
        'return.package.wizard.line', 'wizard_id', string="Packages", readonly=False
    )
    picking_id = fields.Many2one('stock.picking', string="Source Document", readonly=True)
    location_id = fields.Many2one('stock.location', string="Destination Location",  readonly=False)
    lines_computed = fields.Boolean(string="Lines Computed", default=False, readonly=True)
    picking_type_id = fields.Many2one('stock.picking.type', string="Picking Type", readonly=False)

    @api.onchange('picking_id')
    def _compute_location_and_packages(self):
        if self.picking_id:
            self.location_id = self.picking_id.location_id.id
            if not self.lines_computed:
                self.package_line_ids = [(5, 0, 0)]
                move_lines = self.picking_id.move_line_ids
                lines = []
                for move_line in move_lines:
                    lines.append((0, 0, {
                        'select_package': False,
                        'result_package_id': move_line.package_id.id,
                        'location_dest_id': move_line.location_id.id,
                        'pallet_series_id': move_line.x_studio_pallet_series_id,
                        'product_id': move_line.product_id.id,
                        'quantity': move_line.quantity,
                        'expiration_date': move_line.x_studio_expiration_date,
                        'production_date': move_line.x_studio_production_date,
                        'stock_move_line': move_line.id,
                        'return_counter': move_line.x_studio_return_count,
                        'container_number': move_line.x_studio_container_number,
                        'pack_uom_unit': move_line.x_studio_affected_2nd_uom,
                        'min_uom_unit': move_line.x_studio_withdraw_units,
                        'min_uom': move_line.x_studio_min_quantity_uom,
                        'pack_uom': move_line.x_studio_quantity_uom_delivery,
                        'actual_pack_uom_unit': move_line.x_studio_affected_2nd_uom,
                        'actual_min_uom_unit': move_line.x_studio_withdraw_units,
                        'actual_quantity': move_line.quantity,
                        
                    }))
                self.package_line_ids = lines
                self.lines_computed = True

    def action_process_return(self):
        selected_packages = self.package_line_ids.filtered(lambda line: line.select_package)

        if not selected_packages:
            raise UserError("Please select at least 1 Move Line.")
            
        # Guard clause to check synchronization of UoMs in selected packages
        for record in selected_packages:
            if (record.pack_uom_unit < record.actual_pack_uom_unit or
                record.min_uom_unit < record.actual_min_uom_unit or
                record.quantity < record.actual_quantity):
    
                errors = []
    
                # Check which UoMs are not synchronized
                if record.pack_uom_unit == record.actual_pack_uom_unit:
                    errors.append("Packaging Unit")
                if record.min_uom_unit == record.actual_min_uom_unit:
                    errors.append("Minimum Unit")
                if record.quantity == record.actual_quantity:
                    errors.append("Quantity")
    
                # If some values didn't change, raise an error
                if errors:
                    raise UserError(f"The following fields must also be reduced to maintain synchronization: {', '.join(errors)}.")
            # raise UserError(record.actual_pack_uom_unit)

    
        if not self.picking_type_id:
            # Default to the picking type for Receipts if not specified
            warehouse_id = self.picking_id.picking_type_id.warehouse_id.id
            self.picking_type_id = self.env['stock.picking.type'].search([('name', '=', "Receipts"), ('warehouse_id', '=', warehouse_id)], limit=1)
    
        # Copy the picking record
        new_picking = self.picking_id.copy(default={
            'picking_type_id': self.picking_type_id.id,
            'location_dest_id': self.location_id.id,
            'return_id': self.picking_id.id
        })
    
        product_data = {}  # Initialize a dictionary to keep track of quantities, counters, and demand packaging for each product
    
        for package in selected_packages:
            product_id = package.product_id.id
            quantity = package.quantity
            demand_packaging = package.pack_uom_unit
            demand_min = package.min_uom_unit
            pack_uom = package.pack_uom.id,
            min_uom = package.min_uom.id
    
            if product_id not in product_data:
                product_data[product_id] = {
                    'quantity': 0,
                    'counter': 0,
                    'demand_packaging': 0,
                    'demand_min': 0,
                }
    
            # Update the accumulated data
            product_data[product_id]['quantity'] += quantity
            product_data[product_id]['counter'] += 1
            product_data[product_id]['demand_packaging'] += demand_packaging
            product_data[product_id]['demand_min'] += demand_min
            product_data[product_id]['min_uom'] = min_uom
            product_data[product_id]['pack_uom'] = pack_uom
    
        # Remove any existing move lines from the copied picking
        for move_line in new_picking.move_ids_without_package:
            move_line.unlink()
    
        move_line_mapping = {}  # Mapping from product_id to the created move
    
        # Create a stock.move for each product in product_data
        for product_id, data in product_data.items():
            move = self.env['stock.move'].create({
                'name': self.env['product.product'].browse(product_id).display_name,
                'product_id': product_id,
                'product_uom_qty': data['quantity'],
                'product_uom': self.env['product.product'].browse(product_id).uom_id.id,
                'picking_id': new_picking.id,
                'location_id': 4,
                'location_dest_id': new_picking.location_dest_id.id,
                'x_studio_number_of_lines': data['counter'],
                'x_studio_demand_packaging': data['demand_packaging'],
                'x_studio_min_uom': data['demand_min'],
                'x_studio_packaging_unit': data['pack_uom'][0] if isinstance(data['pack_uom'], tuple) and data['pack_uom'] else None,
                'x_studio_min_unit': data['min_uom'][0] if isinstance(data['min_uom'], tuple) and data['min_uom'] else None,
                'reference': new_picking.id,
                'state': 'assigned'
            })
            move_line_mapping[product_id] = move
    
        # Create stock.move.line records for each selected package
        move_line_values = []
        move_line_ids = []
    
        for package in selected_packages:
            move = move_line_mapping.get(package.product_id.id)
            if move:
                move_line_values.append({
                    'move_id': move.id,
                    'product_id': package.product_id.id,
                    'quantity': package.quantity,  # This might need to be 'product_uom_qty' or 'quantity_done' depending on your version
                    'result_package_id': package.result_package_id.id,
                    'location_dest_id': package.location_dest_id.id,
                })
                move_line_ids.append(move.id)
    
        # Create stock.move.line records
        if move_line_values:
            created_move_lines = self.env['stock.move.line'].create(move_line_values)
    
            # Update the additional fields after creation
            for package, move_line in zip(selected_packages, created_move_lines):
                move_line.write({
                    'picking_id': new_picking.id,
                    'x_studio_expiration_date': package.expiration_date,
                    'x_studio_production_date': package.production_date,
                    'x_studio_return_count': package.return_counter + 1,
                    'x_studio_pallet_series_id': package.pallet_series_id,
                    'x_studio_container_number': package.container_number,
                    'x_studio_2nd_uom': package.pack_uom_unit,
                    'x_studio_total_units': package.min_uom_unit,
                    'x_studio_min_quantity_uom': package.min_uom,
                    'x_studio_quantity_uom': package.pack_uom,
                })
    
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Record',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': new_picking.id,
            'target': 'current',
            'state': 'assigned'
        }

    
    

    