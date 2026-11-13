import {
  Button,
  Card,
  CardLoader,
  CardTitle,
  Form,
  FormFieldSecret,
  Link,
  TeamConfigurationSurface,
} from "@netlify/sdk/ui/react/components";
import { ConnectSchema } from "../../schema/team-config.js";
import { trpc } from "../trpc.js";

// The words on this surface are a draft: they wait for the writer agent before the extension is listed.
export const TeamConfiguration = () => {
  const trpcUtils = trpc.useUtils();
  const status = trpc.connection.status.useQuery();
  const refresh = { onSuccess: () => trpcUtils.connection.status.invalidate() };
  const connect = trpc.connection.connect.useMutation(refresh);
  const disconnect = trpc.connection.disconnect.useMutation(refresh);

  if (status.isLoading) {
    return (
      <TeamConfigurationSurface>
        <CardLoader />
      </TeamConfigurationSurface>
    );
  }

  const connected = status.data?.connected === true ? status.data : null;

  return (
    <TeamConfigurationSurface>
      <Card>
        <CardTitle>SpecStream API key</CardTitle>
        {connected ? (
          <>
            <p>
              Connected with the key {connected.keyHint}
              {connected.email ? ` of ${connected.email}` : ""}. Every site of this team reads it from the
              environment variable <code>SPECSTREAM_API_KEY</code> in builds and functions.
            </p>
            <p>To replace the key, paste a new one below.</p>
          </>
        ) : (
          <p>
            Paste a key to make it available to every site of this team as the environment variable{" "}
            <code>SPECSTREAM_API_KEY</code>. Create a key under Agents & API in your{" "}
            <Link href="https://specstream.ai/workspace?utm_source=clouds-31">SpecStream workspace</Link>. New
            accounts start with $10 of credit.
          </p>
        )}
        <Form
          defaultValues={{ apiKey: "" }}
          schema={ConnectSchema}
          onSubmit={async (fields) => {
            await connect.mutateAsync(fields);
          }}
          submitButtonLabel={connected ? "Replace key" : "Connect"}
        >
          <FormFieldSecret
            name="apiKey"
            label="API key"
            helpText="Starts with ss_live_. Netlify stores it as a secret variable. The extension keeps only its last four characters."
          />
        </Form>
        {connected ? (
          <Button
            level="secondary"
            variant="danger"
            loading={disconnect.isPending}
            onClick={() => disconnect.mutate()}
          >
            Disconnect
          </Button>
        ) : null}
        {disconnect.error ? <p>{disconnect.error.message}</p> : null}
      </Card>
    </TeamConfigurationSurface>
  );
};
