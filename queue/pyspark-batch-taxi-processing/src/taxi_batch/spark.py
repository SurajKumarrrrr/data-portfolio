"""SparkSession factory with settings tuned for a single-machine batch job."""

from __future__ import annotations

from pyspark.sql import SparkSession


def get_spark(
    app_name: str = "taxi-batch",
    master: str = "local[*]",
    shuffle_partitions: int = 8,
) -> SparkSession:
    """Build (or reuse) a local SparkSession.

    * ``spark.sql.shuffle.partitions`` is lowered from the default 200, which is far too
      many for a few hundred MB on a laptop and creates thousands of tiny files.
    * Adaptive Query Execution coalesces shuffle partitions and can switch join strategies
      at runtime based on real statistics.
    * The session time zone is pinned to UTC so date/hour derivations are reproducible
      regardless of the machine running the job.
    """
    return (
        SparkSession.builder.appName(app_name)
        .master(master)
        .config("spark.sql.shuffle.partitions", str(shuffle_partitions))
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("spark.ui.enabled", "false")
        .config("spark.ui.showConsoleProgress", "false")
        .getOrCreate()
    )
