from django.shortcuts import render
from rest_framework import viewsets
from .models import (
    Impuesto, ConfiguracionImpuesto, Retencion, ContribucionParafiscal,
    ImpuestoEmpresaActiva, RetencionEmpresaActiva, ContribucionEmpresaActiva,
    EmpresaContribucionParafiscal, ConfiguracionRetencion
)
from .serializers import (
    ImpuestoSerializer, ConfiguracionImpuestoSerializer, RetencionSerializer, ContribucionParafiscalSerializer,
    ImpuestoEmpresaActivaSerializer, RetencionEmpresaActivaSerializer, ContribucionEmpresaActivaSerializer,
    EmpresaContribucionParafiscalSerializer, ConfiguracionRetencionSerializer
)

class ImpuestoViewSet(viewsets.ModelViewSet):
    queryset = Impuesto.objects.all()
    serializer_class = ImpuestoSerializer

class ConfiguracionImpuestoViewSet(viewsets.ModelViewSet):
    queryset = ConfiguracionImpuesto.objects.all()
    serializer_class = ConfiguracionImpuestoSerializer

class RetencionViewSet(viewsets.ModelViewSet):
    queryset = Retencion.objects.all()
    serializer_class = RetencionSerializer

class ContribucionParafiscalViewSet(viewsets.ModelViewSet):
    queryset = ContribucionParafiscal.objects.all()
    serializer_class = ContribucionParafiscalSerializer

class ImpuestoEmpresaActivaViewSet(viewsets.ModelViewSet):
    queryset = ImpuestoEmpresaActiva.objects.all()
    serializer_class = ImpuestoEmpresaActivaSerializer

class RetencionEmpresaActivaViewSet(viewsets.ModelViewSet):
    queryset = RetencionEmpresaActiva.objects.all()
    serializer_class = RetencionEmpresaActivaSerializer

class ContribucionEmpresaActivaViewSet(viewsets.ModelViewSet):
    queryset = ContribucionEmpresaActiva.objects.all()
    serializer_class = ContribucionEmpresaActivaSerializer

class EmpresaContribucionParafiscalViewSet(viewsets.ModelViewSet):
    queryset = EmpresaContribucionParafiscal.objects.all()
    serializer_class = EmpresaContribucionParafiscalSerializer

class ConfiguracionRetencionViewSet(viewsets.ModelViewSet):
    queryset = ConfiguracionRetencion.objects.all()
    serializer_class = ConfiguracionRetencionSerializer
