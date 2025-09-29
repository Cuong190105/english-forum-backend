import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from configs.config_mail import *

EMAIL_CHANGE = "thay đổi email"
PASSWORD_RESET = "khôi phục mật khẩu"
LOGIN = "đăng nhập"

async def __send(content: str, target: str):
    try:
        msg = MIMEText(content, "html", "utf-8")
        msg["From"] = MAIL_FROM_NAME
        msg["To"] = target
        msg["Subject"] = "Password Reset"
        with smtplib.SMTP(MAIL_HOST, MAIL_PORT) as server:
            # server.set_debuglevel(True)
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.sendmail(MAIL_FROM_ADDRESS, target, msg.as_string())
            # server.quit()
    except Exception as e:
        logging.error(f"Failed to send email to {target}: {e}")


async def sendOtpMail(otp: str, username: str, target_address: str, request_type: str):
    warning = "vui lòng bỏ qua email này" if request_type == PASSWORD_RESET else "chúng tôi khuyên bạn nên thay đổi mật khẩu của mình ngay lập tức"
    content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Hỗ trợ tài khoản</title>
        </head>
        <body>
            <div class="card" style="width: 400px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px; font-family: Arial, sans-serif;">
                <p class="greetings">Xin chào {username},</p>
                <p class="message">Chúng tôi vừa nhận được yêu cầu {request_type} cho tài khoản của bạn. Dưới đây là mã xác minh:</p>
                <div class="otp" style="border: 1px solid black; border-radius: 5px; width: 200px; left:100px; position: relative; align-items: center;">
                    <h2 style="text-align: center; margin: 10px 0; letter-spacing: 5px;">{otp}</h2>
                </div>
                <p class="note">Mã này sẽ hết hạn sau 5 phút. Vui lòng không chia sẻ mã này với bất kỳ ai.</p>
                <p class="warning">Nếu bạn không gửi yêu cầu, {warning}.</p>
                <p class="signature">Trân trọng,<br/>Đội ngũ Hỗ trợ English Forum</p>
            </div>
        </body>
        </html>
        """
    
    await __send(content, target_address)

async def sendWarningChangingEmailMail(username, new_email, target_address, cancel_link):
    content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Hỗ trợ tài khoản</title>
        </head>
        <body>
            <div class="card" style="width: 400px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px; font-family: Arial, sans-serif;">
                <p class="greetings">Xin chào {username},</p>
                <p class="message">Chúng tôi vừa nhận được yêu cầu thay đổi địa chỉ email cho tài khoản của bạn.</p>
                <p class="message">Địa chỉ email mới sẽ là: {new_email}.</p>
                <p class="warning">Nếu bạn không gửi yêu cầu này, hãy nhấn vào liên kết dưới đây để hủy thao tác. Đồng thời nhanh chóng đổi mật khẩu cho tài khoản này.</p>
                <div class="link">
                    <a href="">Hủy thao tác</a>
                </div>
                <p class="signature">Trân trọng,<br/>Đội ngũ Hỗ trợ English Forum</p>
            </div>
        </body>
        </html>
        """
    
    await __send(content, target_address)