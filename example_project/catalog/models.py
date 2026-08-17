"""Minimal tenant-scoped models for the example project."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Organization(models.Model):
    name = models.CharField(max_length=64)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="organizations"
    )

    def __str__(self) -> str:
        return self.name


class Item(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=64)
    status = models.CharField(max_length=32, default="active")
    internal_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name
