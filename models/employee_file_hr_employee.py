from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ad_employee_no = fields.Char('رقم الموظف', copy=False, index=True, tracking=True)
    ad_first_name = fields.Char('الاسم الاول')
    ad_mid_name = fields.Char('اسم الاب')
    ad_last_name = fields.Char('اسم الجد')
    ad_surname = fields.Char('اللقب')
    ad_mother_name = fields.Char('اسم الأم')
    ad_previous_job = fields.Char('الوظيفة السابقة')
    ad_work_site_id = fields.Many2one('ad.work.site', string='موقع العمل', tracking=True)
    ad_work_governorate = fields.Char(related='ad_work_site_id.governorate', string='محافظة العمل')
    ad_work_area = fields.Char(related='ad_work_site_id.area', string='منطقة العمل')
    ad_res_governorate = fields.Char('المحافظة')
    ad_res_district = fields.Char('قضاء - ناحية')
    ad_neighborhood = fields.Char('الحي')
    ad_mahalla = fields.Char('المحلة')
    ad_alley = fields.Char('الزقاق')
    ad_house = fields.Char('الدار')
    ad_landmark = fields.Char('اقرب نقطة دالة')
    ad_address = fields.Char('عنوان السكن', compute='_compute_ad_address')
    ad_resid_issuer = fields.Char('بطاقة السكن - جهة الاصدار')
    ad_resid_no = fields.Char('بطاقة السكن - الرقم')
    ad_resid_date = fields.Date('بطاقة السكن - تاريخ الاصدار')
    ad_ration_center = fields.Char('البطاقة التموينية - اسم المركز')
    ad_ration_no = fields.Char('البطاقة التموينية - الرقم')
    ad_ration_date = fields.Date('البطاقة التموينية - تاريخ الاصدار')
    ad_civil_issuer = fields.Char('هوية الاحوال المدنية - جهة الاصدار')
    ad_civil_record_no = fields.Char('هوية الاحوال المدنية - رقم السجل')
    ad_civil_page_no = fields.Char('هوية الاحوال المدنية - رقم الصحيفة')
    ad_nat_issuer = fields.Char('شهادة الجنسية - جهة الاصدار')
    ad_nat_wallet_no = fields.Char('شهادة الجنسية - رقم الحافظة')
    ad_nat_date = fields.Date('شهادة الجنسية - تاريخ الاصدار')
    ad_passport_issuer = fields.Char('جواز السفر - جهة الاصدار')
    ad_passport_no = fields.Char('جواز السفر - الرقم')
    ad_passport_date = fields.Date('جواز السفر - تاريخ الاصدار')
    ad_moi_code = fields.Char('الرمز')
    ad_moi_emp_no = fields.Char('رقم الموظف')
    ad_moi_company_code = fields.Char('الرمز الرقمي للشركة')
    ad_moi_jk_no = fields.Char('رقم JK')
    ad_moi_file_no = fields.Char('رقم الاضبارة - الهوية')

    @api.depends('ad_res_governorate', 'ad_res_district', 'ad_neighborhood', 'ad_mahalla', 'ad_alley', 'ad_house')
    def _compute_ad_address(self):
        for emp in self:
            parts = [emp.ad_res_governorate, emp.ad_res_district, emp.ad_neighborhood, emp.ad_mahalla,
                     emp.ad_alley and 'ز %s' % emp.ad_alley, emp.ad_house and 'د %s' % emp.ad_house]
            emp.ad_address = ' / '.join(p for p in parts if p)

    @api.onchange('name')
    def _onchange_name_split(self):
        for emp in self:
            if emp.name and not (emp.ad_first_name or emp.ad_mid_name or emp.ad_last_name):
                parts = emp.name.split()
                emp.ad_first_name = parts[0] if parts else False
                emp.ad_mid_name = parts[1] if len(parts) > 1 else False
                emp.ad_last_name = parts[2] if len(parts) > 2 else False
                emp.ad_surname = ' '.join(parts[3:]) if len(parts) > 3 else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('ad_employee_no'):
                vals['ad_employee_no'] = self.env['ir.sequence'].next_by_code('ad.hr.employee.no')
        return super().create(vals_list)
