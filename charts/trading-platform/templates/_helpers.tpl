"""
Helm Helper Templates
Common template functions for the trading platform
"""

{{- define "trading-platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "trading-platform.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "trading-platform.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "trading-platform.labels" -}}
helm.sh/chart: {{ include "trading-platform.chart" . }}
{{ include "trading-platform.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "trading-platform.selectorLabels" -}}
app.kubernetes.io/name: {{ include "trading-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "trading-platform.backend.labels" -}}
{{ include "trading-platform.labels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{- define "trading-platform.backend.selectorLabels" -}}
{{ include "trading-platform.selectorLabels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{- define "trading-platform.frontend.labels" -}}
{{ include "trading-platform.labels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{- define "trading-platform.frontend.selectorLabels" -}}
{{ include "trading-platform.selectorLabels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{- define "trading-platform.marketData.labels" -}}
{{ include "trading-platform.labels" . }}
app.kubernetes.io/component: market-data
{{- end }}

{{- define "trading-platform.marketData.selectorLabels" -}}
{{ include "trading-platform.selectorLabels" . }}
app.kubernetes.io/component: market-data
{{- end }}

{{- define "trading-platform.tradingEngine.labels" -}}
{{ include "trading-platform.labels" . }}
app.kubernetes.io/component: trading-engine
{{- end }}

{{- define "trading-platform.tradingEngine.selectorLabels" -}}
{{ include "trading-platform.selectorLabels" . }}
app.kubernetes.io/component: trading-engine
{{- end }}

{{- define "trading-platform.aiEngine.labels" -}}
{{ include "trading-platform.labels" . }}
app.kubernetes.io/component: ai-engine
{{- end }}

{{- define "trading-platform.aiEngine.selectorLabels" -}}
{{ include "trading-platform.selectorLabels" . }}
app.kubernetes.io/component: ai-engine
{{- end }}

{{- define "trading-platform.createSecret" -}}
{{- if not .Values.secrets.existingSecret }}
true
{{- else }}
false
{{- end }}
{{- end }}

{{- define "trading-platform.postgresql.fullname" -}}
{{- if .Values.postgresql.fullnameOverride }}
{{- .Values.postgresql.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default "postgresql" .Values.postgresql.nameOverride }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "trading-platform.redis.fullname" -}}
{{- if .Values.redis.fullnameOverride }}
{{- .Values.redis.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default "redis" .Values.redis.nameOverride }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "trading-platform.mongodb.fullname" -}}
{{- if .Values.mongodb.fullnameOverride }}
{{- .Values.mongodb.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default "mongodb" .Values.mongodb.nameOverride }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "trading-platform.rabbitmq.fullname" -}}
{{- if .Values.rabbitmq.fullnameOverride }}
{{- .Values.rabbitmq.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default "rabbitmq" .Values.rabbitmq.nameOverride }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "trading-platform.getPostgresUser" -}}
{{- if .Values.postgresql.auth.existingSecret }}
{{- $secret := lookup "v1" "Secret" .Release.Namespace .Values.postgresql.auth.existingSecret }}
{{- if $secret }}
{{- index $secret.data "username" | b64dec }}
{{- else }}
{{- .Values.postgresql.auth.username }}
{{- end }}
{{- else }}
{{- .Values.postgresql.auth.username }}
{{- end }}
{{- end }}

{{- define "trading-platform.getPostgresPassword" -}}
{{- if .Values.postgresql.auth.existingSecret }}
{{- $secret := lookup "v1" "Secret" .Release.Namespace .Values.postgresql.auth.existingSecret }}
{{- if $secret }}
{{- index $secret.data "password" | b64dec }}
{{- else }}
{{- .Values.postgresql.auth.password }}
{{- end }}
{{- else }}
{{- .Values.postgresql.auth.password }}
{{- end }}
{{- end }}

{{- define "trading-platform.serviceAccountName" -}}
{{- if .Values.serviceAccounts.create }}
{{- default (include "trading-platform.fullname" .) .Values.serviceAccounts.name }}
{{- else }}
{{- default "default" .Values.serviceAccounts.name }}
{{- end }}
{{- end }}

{{- define "trading-platform.imagePullSecrets" -}}
{{- if .Values.global.imagePullSecrets }}
imagePullSecrets:
{{- range .Values.global.imagePullSecrets }}
  - name: {{ . }}
{{- end }}
{{- else if .Values.image.pullSecrets }}
imagePullSecrets:
{{- range .Values.image.pullSecrets }}
  - name: {{ . }}
{{- end }}
{{- end }}
{{- end }}

{{- define "trading-platform.probes.readiness" -}}
readinessProbe:
  httpGet:
    path: {{ .path | default "/health" }}
    port: {{ .port | default 8000 }}
  initialDelaySeconds: {{ .initialDelaySeconds | default 10 }}
  periodSeconds: {{ .periodSeconds | default 5 }}
  timeoutSeconds: {{ .timeoutSeconds | default 3 }}
  failureThreshold: {{ .failureThreshold | default 3 }}
{{- end }}

{{- define "trading-platform.probes.liveness" -}}
livenessProbe:
  httpGet:
    path: {{ .path | default "/health" }}
    port: {{ .port | default 8000 }}
  initialDelaySeconds: {{ .initialDelaySeconds | default 30 }}
  periodSeconds: {{ .periodSeconds | default 10 }}
  timeoutSeconds: {{ .timeoutSeconds | default 5 }}
  failureThreshold: {{ .failureThreshold | default 3 }}
{{- end }}

{{- define "trading-platform.probes.startup" -}}
startupProbe:
  httpGet:
    path: {{ .path | default "/health" }}
    port: {{ .port | default 8000 }}
  initialDelaySeconds: {{ .initialDelaySeconds | default 10 }}
  periodSeconds: {{ .periodSeconds | default 5 }}
  failureThreshold: {{ .failureThreshold | default 30 }}
{{- end }}

{{- define "trading-platform.resources" -}}
resources:
  requests:
    memory: {{ .requests.memory | default "256Mi" }}
    cpu: {{ .requests.cpu | default "100m" }}
  limits:
    memory: {{ .limits.memory | default "512Mi" }}
    cpu: {{ .limits.cpu | default "250m" }}
{{- end }}

{{- define "trading-platform.podSecurityContext" -}}
podSecurityContext:
  runAsUser: {{ .runAsUser | default 1000 }}
  runAsGroup: {{ .runAsGroup | default 1000 }}
  fsGroup: {{ .fsGroup | default 1000 }}
{{- end }}

{{- define "trading-platform.containerSecurityContext" -}}
securityContext:
  allowPrivilegeEscalation: {{ .allowPrivilegeEscalation | default false }}
  readOnlyRootFilesystem: {{ .readOnlyRootFilesystem | default true }}
  runAsNonRoot: {{ .runAsNonRoot | default true }}
  runAsUser: {{ .runAsUser | default 1000 }}
  capabilities:
    drop:
      - ALL
{{- end }}

{{- define "trading-platform.ingress.annotations" -}}
{{- if .Values.ingress.annotations }}
{{ toYaml .Values.ingress.annotations }}
{{- end }}
{{- end }}

{{- define "trading-platform.ingress.tls" -}}
{{- if .Values.ingress.tls }}
tls:
  {{- range .Values.ingress.tls }}
  - hosts:
    {{- range .hosts }}
      - {{ . | quote }}
    {{- end }}
    secretName: {{ .secretName }}
  {{- end }}
{{- end }}
{{- end }}