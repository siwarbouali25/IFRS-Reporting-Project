from django.urls import path

from data_preparation.api.views import (
    DataUploadBatchBuildCanonicalAPIView,
    DataUploadBatchColumnMappingAPIView,
    DataUploadBatchDetailAPIView,
    DataUploadBatchDetectTablesAPIView,
    DataUploadBatchExtractAPIView,
    DataUploadBatchListCreateAPIView,
    DataUploadBatchValidateCanonicalAPIView,
    DataUploadFileAPIView,
    DataUploadBatchRunNotebookPipelineAPIView
)

app_name = "data_preparation"

urlpatterns = [
    path("batches/", DataUploadBatchListCreateAPIView.as_view(), name="batch-list-create"),
    path("batches/<uuid:batch_id>/", DataUploadBatchDetailAPIView.as_view(), name="batch-detail"),
    path("batches/<uuid:batch_id>/upload/", DataUploadFileAPIView.as_view(), name="batch-upload"),
    path("batches/<uuid:batch_id>/extract/", DataUploadBatchExtractAPIView.as_view(), name="batch-extract"),
    path("batches/<uuid:batch_id>/detect-tables/", DataUploadBatchDetectTablesAPIView.as_view(), name="batch-detect-tables"),
    path("batches/<uuid:batch_id>/column-mapping/",DataUploadBatchColumnMappingAPIView.as_view(),name="batch-column-mapping"),
    path("batches/<uuid:batch_id>/build-canonical/", DataUploadBatchBuildCanonicalAPIView.as_view(), name="batch-build-canonical"),
    path("batches/<uuid:batch_id>/validate-canonical/", DataUploadBatchValidateCanonicalAPIView.as_view(), name="batch-validate-canonical"),
    path("batches/<uuid:batch_id>/run-notebook-pipeline/", DataUploadBatchRunNotebookPipelineAPIView.as_view(), name="batch-run-notebook-pipeline"),
]