import string

from django.conf import settings
from django.db import models
from django.utils import timezone
from datetime import datetime, timedelta
from django.utils.translation import ugettext as _
import hashlib
from garpix_notify.models import Notify
from garpix_utils.string import get_random_string

from garpix_user.exceptions import UserUnregisteredException


class UserEmailConfirmMixin(models.Model):
    """
    Миксин для подтверждения email
    """
    is_email_confirmed = models.BooleanField(_("Email confirmed"), default=False)
    email_confirmation_code = models.CharField(_("Email confirmation code"), max_length=255, blank=True,
                                               null=True)
    email_code_send_date = models.DateTimeField(_("Code sent date"), blank=True, null=True)
    new_email = models.EmailField(_("New email"), blank=True, null=True)

    def send_email_confirmation_code(self, email=None):
        from django.contrib.auth import get_user_model
        from garpix_user.exceptions import UserRegisteredException, WaitException

        User = get_user_model()

        anybody_have_this_email = User.objects.filter(email=email, is_email_confirmed=True).count() > 0
        if anybody_have_this_email:
            return UserRegisteredException(field='email', extra_data={'field': self._meta.get_field('email').verbose_name.title().lower()})

        if settings.GARPIX_USER.get('TIME_LAST_REQUEST', None):
            if self.email_code_send_date and self.email_code_send_date + timedelta(
                    minutes=settings.GARPIX_USER.get('TIME_LAST_REQUEST')) >= datetime.now(self.email_code_send_date.tzinfo):
                return WaitException()

        confirmation_code = get_random_string(settings.GARPIX_USER.get('CONFIRM_CODE_LENGTH', 6), string.digits)

        self.new_email = email or self.email

        self.email_confirmation_code = confirmation_code

        try:
            self.email_code_send_date = timezone.now()
        except Exception:
            self.email_code_send_date = datetime.now()
        self.save()

        print(f'{settings.SITE_URL}/confirm-email/{str(hashlib.sha512(confirmation_code.encode("utf-8")).hexdigest()).lower()}')

        if settings.GARPIX_USER.get('USE_EMAIL_LINK_CONFIRMATION', False):
            hash = str(hashlib.sha512(f'{self.email}+{self.email_confirmation_code}'.encode("utf-8")).hexdigest()).lower()
            Notify.send(settings.EMAIL_LINK_CONFIRMATION_EVENT, {
                'confirmation_link': f'{settings.SITE_URL}/confirm_email/{hash}'
            }, email=self.email)
        else:
            Notify.send(settings.EMAIL_CONFIRMATION_EVENT, {
                'confirmation_code': confirmation_code
            }, email=self.email)

        return True

    def confirm_email(self, email_confirmation_code):
        from garpix_user.exceptions import IncorrectCodeException, NoTimeLeftException

        if self.email_confirmation_code != email_confirmation_code:
            return IncorrectCodeException(field='email_confirmation_code')

        time_is_up = (datetime.now(
            self.email_code_send_date.tzinfo) - self.email_code_send_date).seconds / 60 > settings.GARPIX_USER.get('CONFIRM_EMAIL_CODE_LIFE_TIME', 6)

        if time_is_up:
            return NoTimeLeftException(field='email_confirmation_code')

        self.is_email_confirmed = True
        self.email = self.new_email
        self.save()
        return True

    @classmethod
    def confirm_email_by_link(cls, hash):
        from garpix_user.exceptions import IncorrectCodeException, NoTimeLeftException

        users_list = cls.objects.filter(is_email_confirmated=False)

        for user in users_list:
            if str(hashlib.sha512(f'{user.email}+{user.email_confirmation_code}'.encode("utf-8")).hexdigest()).lower() == hash:
                time_is_up = (datetime.now(
                    user.email_code_send_date.tzinfo) - user.email_code_send_date).seconds / 60 > settings.GARPIX_USER.get(
                    'CONFIRM_EMAIL_CODE_LIFE_TIME', 6)
                if time_is_up:
                    return NoTimeLeftException(field='email_confirmation_code')
                user.is_email_confirmed = True
                user.email = user.new_email
                user.save()
                return True

        return IncorrectCodeException(field='email_confirmation_code')

    def check_email_confirmation(self):
        return self.is_email_confirmed

    class Meta:
        abstract = True
