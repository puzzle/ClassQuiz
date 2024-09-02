import dagger
from dagger import dag, function, object_type

@object_type
class ClassQuiz:

    @function
    async def build(self, context: dagger.Directory) -> dagger.Container:
        """Returns a container built with the given context."""
        return await dag.container().build(context)

    @function
    async def vulnerability_scan(self, context: dagger.Directory) -> dagger.Directory:
        """Builds the front- and backend, performs a Trivy scan and returns the directory containing the reports."""
        trivy = dag.trivy()

        directory = (
            dag.directory()
            .with_file("scans/backend.sarif", trivy.container(await self.build(context)).report("sarif"))
            .with_file("scans/frontend.sarif", trivy.container(await self.build(context.directory("frontend"))).report("sarif"))
        )
        return directory

    @function
    def frontend(self, context: dagger.Directory) -> dagger.Service:
        """Returns a frontend service from a container built with the given context and params."""
        return (
            dag.container()
            .with_env_variable("API_URL", "http://api:8081")
            .with_env_variable("REDIS_URL", "redis://redisd:6379/0?decode_responses=True")
            .build(context)
            .as_service()
        )

    @function
    def backend(self, context: dagger.Directory) -> dagger.Service:
        """Returns a backend service from a container built with the given context, params and service bindings."""
        return (
            dag.container()
            .with_env_variable("MAX_WORKERS", "1")
            .with_env_variable("PORT", "8081")
            .with_service_binding("postgresd", self.postgres())
            .with_service_binding("meilisearchd", self.meilisearch())
            .with_service_binding("redisd", self.redis())
            .build(context)
            .as_service()
        )

    @function
    def postgres(self) -> dagger.Service:
        """Returns a postgres database service from a container built with the given params."""
        return (
            dag.container()
            .from_("postgres:14-alpine")
            .with_env_variable("POSTGRES_PASSWORD", "classquiz")
            .with_env_variable("POSTGRES_DB", "classquiz")
            .with_env_variable("POSTGRES_USER", "postgres")
            .with_exposed_port(5432)
            .as_service()
        )

    @function
    def meilisearch(self) -> dagger.Service:
        """Returns a meilisearch service from a container built with the given params."""
        return (
            dag.container()
            .from_("getmeili/meilisearch:v0.28.0")
            .with_exposed_port(7700)
            .as_service()
        )

    @function
    def redis(self) -> dagger.Service:
        """Returns a redis service from a container built with the given params."""
        return (
            dag.container()
            .from_("redis:alpine")
            .with_exposed_port(6379)
            .as_service()
        )

    @function
    def proxy(self, context: dagger.Directory, proxy_config: dagger.File) -> dagger.Service:
        """Returns a caddy proxy service encapsulating the front and backend services. This service must be bound to port 8000 in order to match some hard coded configuration: --ports 8000:8080"""
        return (
            dag.container()
            .from_("caddy:alpine")
            .with_service_binding("frontend", self.frontend(context.directory("frontend")))
            .with_service_binding("api", self.backend(context))
            .with_file("/etc/caddy/Caddyfile", proxy_config)
            .with_exposed_port(8080)
            .as_service()
        )
