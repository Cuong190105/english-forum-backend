import aiosmtplib
import logging
from email.message import EmailMessage
from configs.config_mail import *

EMAIL_CHANGE = "thay đổi email"
PASSWORD_RESET = "khôi phục mật khẩu"
LOGIN = "đăng nhập"
REGISTER = "đăng ký"

async def send(subject: str, content: str, target: str):
    try:
        msg = EmailMessage()
        # msg = MIMEText(content, "html", "utf-8")
        msg["From"] = MAIL_FROM_NAME
        msg["To"] = target
        msg["Subject"] = subject

        msg.set_content(content, subtype='html')

        await aiosmtplib.send(
            msg,
            hostname=MAIL_HOST,
            port=MAIL_PORT,
            start_tls=True,
            username=MAIL_USERNAME,
            password=MAIL_PASSWORD,
        )
        # with smtplib.SMTP(MAIL_HOST, MAIL_PORT) as server:
            # server.set_debuglevel(True)
        #     server.starttls()
        #     server.login(MAIL_USERNAME, MAIL_PASSWORD)
        #     server.sendmail(MAIL_FROM_ADDRESS, target, msg.as_string())
    except aiosmtplib.SMTPRecipientRefused as e:
        logging.error(f"Failed to send email to {target}: {e}")
        raise Exception("Failed to send email to " + target)


async def sendOtpMail(otp: str, username: str, target_address: str, request_type: str):
    warning = "vui lòng bỏ qua email này" if request_type == PASSWORD_RESET else "chúng tôi khuyên bạn nên thay đổi mật khẩu của mình ngay lập tức"
    subject = ""
    if request_type == REGISTER:
        subject = "Chào mừng đến với English Forum!"
        message = "Chào mừng bạn đến với English Forum. Để tiếp tục, bạn cần nhập mã xác minh để chắc chắn rằng bạn có thể truy cập được vào địa chỉ email này"
    else:
        subject = f"Yêu cầu {request_type}."
        message = f"Chúng tôi vừa nhận được yêu cầu {request_type} cho tài khoản của bạn"
    
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
                <p class="message">{message}. Dưới đây là mã xác minh:</p>
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
    
    await send(subject, content, target_address)

async def sendWarningChangingEmailMail(username, new_email, target_address, cancel_link):
    subject = "Cảnh báo thay đổi email"

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
                    <a href="{cancel_link}">Hủy thao tác</a>
                </div>
                <p class="signature">Trân trọng,<br/>Đội ngũ Hỗ trợ English Forum</p>
            </div>
        </body>
        </html>
        """
    
    await send(subject, content, target_address)