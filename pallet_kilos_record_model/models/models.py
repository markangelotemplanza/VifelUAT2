# -*- coding: utf-8 -*-

from odoo import models, fields, api


class pallet_kilos_record_model(models.Model):
    _name = 'pallet_kilos_record_model.pallet_kilos_record_model'
    _description = 'pallet_kilos_record_model.pallet_kilos_record_model'
    
    report_no = fields.Char(string="Report No.")
    owner_id = fields.Many2one('res.partner', 'Owner')
    warehouse = fields.Many2one('stock.warehouse', 'Warehouse')
    record_reference = fields.Many2one('stock.picking', 'Record Reference')
    overall_kilos = fields.Float(store=True, string="Overall Kilos", group_operator=False)
    overall_pallets = fields.Float(store=True, string="Overall Pallets", group_operator=False)
    pallets_received = fields.Float(store=True, string="Pallets Received", group_operator=False)
    pallets_withdrawn = fields.Float(store=True, string="Pallets Withdrawn", group_operator=False)
    kilos_received = fields.Float(store=True, string="Kilos Received", group_operator=False)
    kilos_withdrawn = fields.Float(store=True, string="Kilos Withdrawn", group_operator=False)
    total_balance_in_kilos = fields.Float(store=True, string="Total Balance in Kilos (KG)", group_operator=False)
    total_balance_in_pallets= fields.Float(store=True, string="Total Balance in Pallets", group_operator=False)
    holding_rate = fields.Float(string='Holding Rate', related='owner_id.x_studio_holding_rate')
    handling_rate = fields.Float(string='Handling Rate', related='owner_id.x_studio_handling_rate')
    

    @api.model
    def _max_pallets(self):
        return self.env['x_inventory_static_var'].search(['&', ('x_studio_use_case', '=', 'XLSX Variables'), ('x_name', 'ilike', 'Max Pallets')], limit=1)
    @api.model
    def _max_kg(self):
        return self.env['x_inventory_static_var'].search(['&', ('x_studio_use_case', '=', 'XLSX Variables'), ('x_name', 'ilike', 'Max Kilograms')], limit=1)
        
    max_pallets = fields.Many2one('x_inventory_static_var', 'Max Pallets', default=_max_pallets)
    max_pallets = fields.Many2one('x_inventory_static_var', 'Max Kilograms', default=_max_kg)

