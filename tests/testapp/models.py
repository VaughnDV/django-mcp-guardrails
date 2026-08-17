"""Synthetic multi-tenant models for Django integration tests."""

from __future__ import annotations

from django.db import models


class Organization(models.Model):
    name = models.CharField(max_length=64)

    class Meta:
        app_label = "testapp"


class Industry(models.Model):
    name = models.CharField(max_length=64)

    class Meta:
        app_label = "testapp"


class CatalogItem(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    industry = models.ForeignKey(Industry, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=64)
    status = models.CharField(max_length=32, default="active")
    secret_note = models.CharField(max_length=64, default="hidden")
    date_added = models.DateField(null=True)

    class Meta:
        app_label = "testapp"
        ordering = ["id"]
