from odoo import models
import datetime
from xlsxwriter.workbook import Workbook

class PalletKilosXlsx(models.AbstractModel):
    _name = 'report.pallet_kilos_record_model.pallet_kilos_report_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def _define_formats(self, workbook):
        """Define and return format objects."""
        header_format = workbook.add_format({'font_size': 12, 'align': 'vcenter', 'bold': True, 'text_wrap': True})
        table_header_format = workbook.add_format({'font_size': 12, 'align': 'vcenter', 'bold': True, 'text_wrap': True, 'border': 1})
        normal_format = workbook.add_format({'font_size': 12, 'align': 'vcenter'})
        float_format = workbook.add_format({'font_size': 12, 'align': 'vcenter', 'num_format': '#,##0.00'})
        float_format_bold = workbook.add_format({'font_size': 12, 'align': 'vcenter', 'num_format': '#,##0.00', 'bold': True})
        date_format = workbook.add_format({'num_format': 'mm/dd/yy'})
        return header_format, table_header_format, normal_format, float_format, float_format_bold, date_format

    def generate_header(self, sheet, sorted_records, formats):
        """Generate header section of the report."""
        header_format, _, normal_format, _, _, _ = formats
        sheet.write(0, 0, sorted_records[0].owner_id.name or '', header_format)
        sheet.write(1, 0, 'BILLING DETAILS-HOLDING', normal_format)
        start_date = sorted_records[0].create_date + datetime.timedelta(hours=8)
        end_date = sorted_records[-1].create_date + datetime.timedelta(hours=8)
        date_range = start_date.strftime('%B %d, %Y') + ' - ' + end_date.strftime('%B %d, %Y')
        sheet.write(2, 0, date_range)

    def generate_table_header(self, sheet, row_index, formats):
        """Generate table header."""
        _, table_header_format, _, _, _, _ = formats
        table_headers = ['Date', 'Receiving Report No.', 'Withdrawal Report No.', 'Pallets Received', 'Pallets Withdrawn', 'Balance in Pallets', 'Kilos Received', 'Kilos Withdrawn', 'Balance in Kilos', 'HOLDING RATE/day/pallet', 'HANDLING RATE']
        col_index = 0
        for header_text in table_headers:
            sheet.write(row_index, col_index, header_text, table_header_format)
            col_index += 1

    def generate_xlsx_report(self, workbook, data, records):
        """Generate the entire XLSX report."""
        formats = self._define_formats(workbook)
        header_format, table_header_format, normal_format, float_format, float_format_bold, date_format = formats
    
        # Group records by owner
        records_by_owner = {}
        for record in records:
            owner_name = record.owner_id.name or 'Unknown'
            if owner_name not in records_by_owner:
                records_by_owner[owner_name] = []
            records_by_owner[owner_name].append(record)
    
        # Iterate over each owner and generate a separate sheet
        for owner_name, owner_records in records_by_owner.items():
            # Create a new worksheet for the owner
            sheet = workbook.add_worksheet(owner_name)
            sheet.set_column(0, 11, 23)
            row_index = 5
    
            # Sort records by date
            sorted_records = sorted(owner_records, key=lambda x: x.create_date)
    
            # Determine the oldest and latest date
            oldest_date = sorted_records[0].create_date.date()
            latest_date = sorted_records[-1].create_date.date()
    
            # Create a list of all dates between oldest_date and latest_date
            date_list = [oldest_date + datetime.timedelta(days=x) for x in range((latest_date - oldest_date).days + 1)]
    
            # Prepare a lookup dictionary for records by date
            records_by_date = {}
            for record in sorted_records:
                record_date = record.create_date.date()
                if record_date not in records_by_date:
                    records_by_date[record_date] = []
                records_by_date[record_date].append(record)
    
            # Generate header and table header
            self.generate_header(sheet, sorted_records, formats)
            self.generate_table_header(sheet, row_index - 2, formats)
    
            # Initialize summation dictionary
            summation = {'total_pallets_received': 0, 'total_pallets_withdrawn': 0, 'total_kilos_received': 0, 'total_kilos_withdrawn': 0}
    
            # Iterate over the full date range
            for current_date in date_list:
                # Get all records for the current date, or an empty list if none exist
                records_for_date = records_by_date.get(current_date, [])
    
                # Write a row for each record on the current date
                for line in records_for_date:
                    # Ensure proper formatting and summation
                    create_date = (current_date + datetime.timedelta(hours=8)) if current_date else ''
                    sheet.write(row_index, 0, create_date, date_format)
                    sheet.write(row_index, 1 if 'RR' in (line.record_reference.name if line.record_reference else '') else 2, line.record_reference.name if line else '', normal_format)
                    sheet.write(row_index, 3, line.pallets_received or 0, float_format)
                    sheet.write(row_index, 4, line.pallets_withdrawn or 0, float_format)
                    sheet.write(row_index, 5, line.total_balance_in_pallets or 0, float_format)
                    sheet.write(row_index, 6, line.kilos_received or 0, float_format)
                    sheet.write(row_index, 7, line.kilos_withdrawn or 0, float_format)
                    sheet.write(row_index, 8, line.total_balance_in_kilos or 0, float_format)
                    sheet.write(row_index, 9, line.holding_rate or 0, float_format)
                    sheet.write(row_index, 10, line.handling_rate or 0, float_format)
    
                    # Sum up various properties
                    summation['total_pallets_received'] += line.pallets_received or 0
                    summation['total_pallets_withdrawn'] += line.pallets_withdrawn or 0
                    summation['total_kilos_received'] += line.kilos_received or 0
                    summation['total_kilos_withdrawn'] += line.kilos_withdrawn or 0
    
                    # Increment row index
                    row_index += 1
    
                # If no records for the current date, write a blank row
                if not records_for_date:
                    create_date = (current_date + datetime.timedelta(hours=8))
                    sheet.write(row_index, 0, create_date, date_format)
                    # Write blank data for the rest of the columns
                    sheet.write(row_index, 1, '', normal_format)
                    sheet.write(row_index, 3, 0, float_format)
                    sheet.write(row_index, 4, 0, float_format)
                    sheet.write(row_index, 5, 0, float_format)
                    sheet.write(row_index, 6, 0, float_format)
                    sheet.write(row_index, 7, 0, float_format)
                    sheet.write(row_index, 8, 0, float_format)
                    sheet.write(row_index, 9, 0, float_format)
                    sheet.write(row_index, 10, 0, float_format)
    
                    # Increment row index
                    row_index += 1
    
            # Write summation totals
            sheet.write(row_index, 3, summation['total_pallets_received'], float_format_bold)
            sheet.write(row_index, 4, summation['total_pallets_withdrawn'], float_format_bold)
            sheet.write(row_index, 6, summation['total_kilos_received'], float_format_bold)
            sheet.write(row_index, 7, summation['total_kilos_withdrawn'], float_format_bold)
    
            sheet.write(row_index + 3, 0, "GUARANTEED", header_format)
