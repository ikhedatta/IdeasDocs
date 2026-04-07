interface CredentialFormProps {
  authMethod: string;
  sourceType: string;
  credentials: Record<string, string>;
  onChange: (creds: Record<string, string>) => void;
}

/* Field definitions per auth method + source overrides */
const AUTH_FIELDS: Record<string, { key: string; label: string; type?: string }[]> = {
  api_key: [{ key: 'api_token', label: 'API Token', type: 'password' }],
  oauth2: [
    { key: 'access_token', label: 'Access Token', type: 'password' },
    { key: 'refresh_token', label: 'Refresh Token (optional)', type: 'password' },
  ],
  access_key: [
    { key: 'access_key_id', label: 'Access Key ID' },
    { key: 'secret_access_key', label: 'Secret Access Key', type: 'password' },
  ],
  service_account: [
    { key: 'service_account_json', label: 'Service Account JSON', type: 'password' },
  ],
  bot_token: [{ key: 'bot_token', label: 'Bot Token', type: 'password' }],
  basic: [
    { key: 'email', label: 'Email' },
    { key: 'api_token', label: 'API Token / Password', type: 'password' },
  ],
  app_password: [
    { key: 'username', label: 'Username' },
    { key: 'app_password', label: 'App Password', type: 'password' },
  ],
};

/* Some sources need extra fields on top of the auth method */
const SOURCE_EXTRA_FIELDS: Record<string, { key: string; label: string; type?: string }[]> = {
  confluence: [{ key: 'email', label: 'Atlassian Email' }],
  jira: [{ key: 'email', label: 'Atlassian Email' }],
  zendesk: [{ key: 'email', label: 'Zendesk Agent Email' }],
};

export function CredentialForm({
  authMethod,
  sourceType,
  credentials,
  onChange,
}: CredentialFormProps) {
  const baseFields = AUTH_FIELDS[authMethod] || AUTH_FIELDS.api_key;
  const extraFields = SOURCE_EXTRA_FIELDS[sourceType] || [];
  const fields = [...extraFields, ...baseFields];

  const handleChange = (key: string, value: string) => {
    onChange({ ...credentials, [key]: value });
  };

  return (
    <div className="space-y-3">
      {fields.map((field) => (
        <div key={field.key}>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {field.label}
          </label>
          <input
            type={field.type || 'text'}
            value={credentials[field.key] || ''}
            onChange={(e) => handleChange(field.key, e.target.value)}
            className="w-full px-3 py-2 border rounded-lg text-sm"
            placeholder={field.label}
            autoComplete="off"
          />
        </div>
      ))}
    </div>
  );
}
