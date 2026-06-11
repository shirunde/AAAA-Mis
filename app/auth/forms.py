"""认证模块表单"""
from wtforms import Form, StringField, PasswordField, SelectField
from wtforms.validators import DataRequired, Length, EqualTo, Regexp, Optional, ValidationError


def _optional_int(value):
    """SelectField 空选项兼容：'' -> None，避免 coerce=int 校验失败"""
    if value is None or value == '':
        return None
    return int(value)


def _require_student_fields(form, field):
    """学生注册时必须选择专业与班级；教师角色跳过"""
    if form.role.data != 'student':
        return
    if field.data is None:
        raise ValidationError('请选择' + field.label.text)


class LoginForm(Form):
    username = StringField('用户名', validators=[DataRequired('请输入用户名')])
    password = PasswordField('密码', validators=[DataRequired('请输入密码')])


class RegisterForm(Form):
    username = StringField('用户名', validators=[
        DataRequired('请输入用户名'),
        Length(min=3, max=50, message='用户名长度3-50个字符'),
        Regexp(r'^[a-zA-Z0-9_]+$', message='用户名只能包含字母、数字和下划线')
    ])
    password = PasswordField('密码', validators=[
        DataRequired('请输入密码'),
        Length(min=6, max=30, message='密码长度6-30个字符')
    ])
    password2 = PasswordField('确认密码', validators=[
        DataRequired('请再次输入密码'),
        EqualTo('password', message='两次输入的密码不一致')
    ])
    role = SelectField('角色', choices=[
        ('student', '学生'),
        ('teacher', '教师')
    ], validators=[DataRequired('请选择角色')])

    # 学生/教师共用基本信息
    name = StringField('姓名', validators=[DataRequired('请输入姓名')])
    gender = SelectField('性别', choices=[('M', '男'), ('F', '女')])
    major_id = SelectField('专业', choices=[], coerce=_optional_int,
                           validators=[_require_student_fields])
    class_id = SelectField('班级', choices=[], coerce=_optional_int,
                           validators=[_require_student_fields])
    phone = StringField('电话', validators=[Optional(), Length(max=20)])
    email = StringField('邮箱', validators=[Optional(), Length(max=100)])
