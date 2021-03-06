from django.http import HttpResponsePermanentRedirect
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import smart_str, smart_bytes, DjangoUnicodeDecodeError
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from drf_yasg import openapi
from django.conf import settings
from django.urls import reverse
from django.contrib.sites.shortcuts import get_current_site
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from rest_framework import generics, status, views
import jwt
from decouple import config

from .models import *
from .utils import Util
from .serializers import *
from .renderers import UserRenderer


class RegisterAPIView(generics.GenericAPIView):

    serializer_class = RegisterUserSerializer
    renderer_classes = (UserRenderer,)

    def post(self, request):
        user = request.data
        email = request.data.get('email')
        if not User.objects.filter(email=email).exists():
            serializer = self.serializer_class(data=user)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            user_data = serializer.data
            user = User.objects.get(email=user_data['email'])
            user.is_active = False
            token = RefreshToken.for_user(user).access_token
            current_site = get_current_site(request).domain
            relativeLink = reverse('email-verify')
            absurl = 'http://'+current_site+relativeLink+"?token="+str(token)
            email_body = 'Hi '+user.name + \
                ' Use the link below to verify your email \n' + absurl
            data = {'email_body': email_body, 'to_email': [user.email],
                    'email_subject': 'Verify your email'}

            Util.send_email(data)
            response = {
                "msg": "Verification e-mail sent, please verify your mail to activate your account",
            }
            return Response(response, status.HTTP_201_CREATED)
        else:
            response = {
                "msg": "User already exists",
            }
            return Response(response, status.HTTP_409_CONFLICT)

class VerifyEmailView(views.APIView):
    serializer_class = EmailVerificationSerializer
    renderer_classes = (UserRenderer,)

    token_param_config = openapi.Parameter(
        'token', in_=openapi.IN_QUERY, description='Description', type=openapi.TYPE_STRING)

    def get(self, request):
        token = request.GET.get('token')
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=['HS256'])
            user = User.objects.get(id=payload['user_id'])
            if not user.is_active:
                user.is_active = True
                user.save()
            return HttpResponsePermanentRedirect(config('FRONTEND_URL') + '/account/email_valid/true')
        except jwt.ExpiredSignatureError as identifier:
            return HttpResponsePermanentRedirect(config('FRONTEND_URL') + '/account/email_valid/expired')
        except jwt.exceptions.DecodeError as identifier:
            return HttpResponsePermanentRedirect(config('FRONTEND_URL') + '/account/email_valid/invalid')


class LoginAPIView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    renderer_classes = (UserRenderer,)

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LogoutAPIView(generics.GenericAPIView):
    serializer_class = LogoutSerializer
    renderer_classes = (UserRenderer,)

    def post(self, request):

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(status=status.HTTP_204_NO_CONTENT)


class RequestPasswordResetEmail(generics.GenericAPIView):
    serializer_class = ResetPasswordEmailRequestSerializer
    renderer_classes = (UserRenderer,)

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        email = request.data.get('email', '')
        if User.objects.filter(email=email).exists():
            user = User.objects.get(email=email)
            uidb64 = urlsafe_base64_encode(smart_bytes(user.id))
            token = PasswordResetTokenGenerator().make_token(user)
            absurl = config('FRONTEND_URL') + '/password_reset/' + uidb64 + '/' + token
            email_body = 'Hello, \n Use link below to reset your password  \n' + absurl
            data = {'email_body': email_body, 'to_email': [user.email],
                    'email_subject': 'Reset your passsword'}
            Util.send_email(data)
        return Response({'success': 'We have sent you a link to reset your password'}, status=status.HTTP_200_OK)


class SetNewPasswordAPIView(generics.GenericAPIView):
    serializer_class = SetNewPasswordSerializer
    renderer_classes = (UserRenderer,)

    def patch(self, request, uidb64, token):
        try:
            print(request.data)
            id = smart_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(id=id)
            if not PasswordResetTokenGenerator().check_token(user, token):
                return Response({'message': 'Token is invalid please request a new one'}, status=status.HTTP_401_UNAUTHORIZED)
            user.set_password(request.data['password'])
            user.save()
            return Response({'message': 'Password reset success'}, status=status.HTTP_200_OK)
        except DjangoUnicodeDecodeError as identifier:
            return Response({
                'message': 'Token is invalid please request a new one'
            }, status=status.HTTP_401_UNAUTHORIZED)

class ChangePasswordView(generics.UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    model = User
    renderer_classes = (UserRenderer,)

    def get_object(self, queryset=None):
        obj = self.request.user
        return obj

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            if not self.object.check_password(serializer.data.get("old_password")):
                return Response({"old_password": ["Wrong password."]}, status=status.HTTP_400_BAD_REQUEST)

            self.object.set_password(serializer.data.get("new_password"))
            self.object.save()
            response = {
                'message': 'Password updated successfully',
            }

            return Response(response, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
