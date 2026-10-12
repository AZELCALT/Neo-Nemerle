using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Threading.Tasks;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using NuGet.Common;
using NuGet.Configuration;
using NuGet.Frameworks;
using NuGet.Packaging;
using NuGet.Protocol;
using NuGet.Protocol.Core.Types;
using NuGet.Versioning;
using static Nemerle.Scripting.contracts;
using static Nemerle.Scripting.dependencies;

namespace Nemerle.Scripting.NuGet
{
    // This optional adapter owns package-library APIs. The compiler sees only
    // the resolver contract and concrete compile/runtime/native asset paths.
    public sealed class NuGetScriptResolver : IScriptDependencyResolver
    {
        readonly string cache;
        readonly string[] feeds;
        readonly object gate = new object();
        public bool Offline { get; set; }
        public bool UpdateLock { get; set; }
        public sealed class LockedPackage
        {
            public string Id { get; set; }
            public string Version { get; set; }
            public string Feed { get; set; }
            public string Hash { get; set; }
        }
        sealed class ExplicitHttpHandlerProvider : ResourceProvider
        {
            public ExplicitHttpHandlerProvider() : base(typeof(HttpHandlerResource), nameof(ExplicitHttpHandlerProvider)) { }
            public override Task<Tuple<bool, INuGetResource>> TryCreate(SourceRepository source, CancellationToken cancellation)
            {
                cancellation.ThrowIfCancellationRequested();
                var handler = new HttpClientHandler();
                return Task.FromResult(Tuple.Create(true, (INuGetResource)new HttpHandlerResourceV3(handler, handler)));
            }
        }
        sealed class Package
        {
            public LockedPackage Record;
            public string Directory;
            public Dictionary<string, VersionRange> Dependencies;
        }
        public NuGetScriptResolver(string cacheDirectory, string[] repositories)
        {
            cache = Path.GetFullPath(cacheDirectory);
            feeds = repositories.Length == 0 ? new[] { "https://api.nuget.org/v3/index.json" } : repositories.ToArray();
        }
        static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes));
        public ScriptResolution Resolve(ScriptCollectedData data, ScriptDefinition definition, CancellationToken cancellation)
        {
            lock (gate)
            {
                try { return ResolveCore(data, definition, cancellation); }
                catch (OperationCanceledException) { throw; }
                catch (ScriptDependencyException) { throw; }
                catch (Exception error)
                {
                    var location = data.Packages.Count == 0 ? new ScriptDiagnostic(data.Source.Path, 1, 1, "", false) : data.Packages[0].Location;
                    throw new ScriptDependencyException(new ScriptDiagnostic(location.File, location.Line, location.Column, error.Message, true));
                }
            }
        }
        ScriptResolution ResolveCore(ScriptCollectedData data, ScriptDefinition definition, CancellationToken cancellation)
        {
            var framework = NuGetFramework.ParseFolder(definition.TargetFramework);
            var roots = new Dictionary<string, NuGetVersion>(StringComparer.OrdinalIgnoreCase);
            foreach (var request in data.Packages)
            {
                PackageIdValidator.ValidatePackageId(request.Id);
                if (!NuGetVersion.TryParse(request.Version, out var version) || request.Version.Contains('*'))
                    throw new InvalidDataException("Expected an exact package version: " + request.Id);
                if (roots.TryGetValue(request.Id, out var existing) && existing != version)
                    throw new InvalidDataException("Conflicting root versions for " + request.Id);
                roots[request.Id] = version;
            }
            var sources = feeds.Concat(data.Repositories).Distinct(StringComparer.Ordinal).ToArray();
            var key = Hash(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new {
                Version = 1, Framework = definition.TargetFramework, Runtime = definition.RuntimeIdentifier,
                Sources = sources, Roots = roots.OrderBy(x => x.Key, StringComparer.OrdinalIgnoreCase).Select(x => x.Key.ToLowerInvariant() + "/" + x.Value.ToNormalizedString()).ToArray()
            })));
            var lockPath = Path.Combine(cache, "locks", key + ".json");
            using var sourceCache = new SourceCacheContext { NoCache = true, DirectDownload = true };
            var resources = new Dictionary<string, FindPackageByIdResource>();
            FindPackageByIdResource Resource(string feed)
            {
                if (Offline && Uri.TryCreate(feed, UriKind.Absolute, out var uri) && !uri.IsFile)
                    throw new InvalidDataException("Offline dependency is unavailable locally");
                if (!resources.TryGetValue(feed, out var resource))
                {
                    if (!Uri.TryCreate(feed, UriKind.Absolute, out var sourceUri) || sourceUri.IsFile)
                        resource = new LocalV2FindPackageByIdResource(new PackageSource(sourceUri != null && sourceUri.IsFile ? sourceUri.LocalPath : Path.GetFullPath(feed)));
                    else
                    {
                        var providers = new INuGetResourceProvider[] {
                            new FeedTypeResourceProvider(), new ServiceIndexResourceV3Provider(),
                            new HttpSourceResourceProvider(), new ExplicitHttpHandlerProvider(),
                            new HttpFileSystemBasedFindPackageByIdResourceProvider(), new RemoteV3FindPackageByIdResourceProvider(), new RegistrationResourceV3Provider()
                        };
                        resource = new SourceRepository(new PackageSource(feed), providers).GetResourceAsync<FindPackageByIdResource>(cancellation).GetAwaiter().GetResult();
                    }
                    resources.Add(feed, resource);
                }
                return resource;
            }
            var loaded = new Dictionary<string, Package>(StringComparer.OrdinalIgnoreCase);
            Package Read(string id, NuGetVersion version, string preferredFeed = null, string expectedHash = null)
            {
                cancellation.ThrowIfCancellationRequested();
                PackageIdValidator.ValidatePackageId(id);
                var identity = id.ToLowerInvariant() + "/" + version.ToNormalizedString();
                if (loaded.TryGetValue(identity, out var found)) return found;
                var directory = Path.Combine(cache, "packages", id.ToLowerInvariant(), version.ToNormalizedString());
                var archive = Path.Combine(directory, "package.nupkg");
                var origin = Path.Combine(directory, "feed.txt");
                string selectedFeed = preferredFeed;
                if (!File.Exists(archive))
                {
                    byte[] bytes = null;
                    foreach (var feed in preferredFeed == null ? sources : new[] { preferredFeed })
                    {
                        if (Offline && Uri.TryCreate(feed, UriKind.Absolute, out var uri) && !uri.IsFile) continue;
                        using var stream = new MemoryStream();
                        if (Resource(feed).CopyNupkgToStreamAsync(id, version, stream, sourceCache, NullLogger.Instance, cancellation).GetAwaiter().GetResult())
                        { bytes = stream.ToArray(); selectedFeed = feed; break; }
                    }
                    if (bytes == null) throw new FileNotFoundException("Package unavailable: " + identity + (Offline ? " (offline)" : ""));
                    if (expectedHash != null && Hash(bytes) != expectedHash) throw new InvalidDataException("Locked package content changed: " + identity);
                    var pending = directory + ".pending-" + Guid.NewGuid().ToString("N");
                    Directory.CreateDirectory(pending);
                    try
                    {
                        using var zip = new ZipArchive(new MemoryStream(bytes));
                        foreach (var entry in zip.Entries)
                        {
                            cancellation.ThrowIfCancellationRequested();
                            var destination = Path.GetFullPath(Path.Combine(pending, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                            if (!destination.StartsWith(pending + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new InvalidDataException("Unsafe package entry");
                            if (entry.FullName.EndsWith("/", StringComparison.Ordinal)) { Directory.CreateDirectory(destination); continue; }
                            Directory.CreateDirectory(Path.GetDirectoryName(destination));
                            using var input = entry.Open(); using var output = File.Create(destination); input.CopyTo(output);
                        }
                        File.WriteAllBytes(Path.Combine(pending, "package.nupkg"), bytes);
                        File.WriteAllText(Path.Combine(pending, "feed.txt"), selectedFeed);
                        Directory.CreateDirectory(Path.GetDirectoryName(directory));
                        try { Directory.Move(pending, directory); }
                        catch (IOException) when (Directory.Exists(directory)) { }
                    }
                    finally { if (Directory.Exists(pending)) Directory.Delete(pending, true); }
                }
                var digest = Hash(File.ReadAllBytes(archive));
                if (expectedHash != null && digest != expectedHash) throw new InvalidDataException("Locked package content changed: " + identity);
                using var reader = new PackageArchiveReader(archive);
                var actual = reader.GetIdentity();
                if (!actual.Id.Equals(id, StringComparison.OrdinalIgnoreCase) || actual.Version != version) throw new InvalidDataException("Package identity mismatch");
                var groups = reader.NuspecReader.GetDependencyGroups().ToArray();
                var nearest = new FrameworkReducer().GetNearest(framework, groups.Select(x => x.TargetFramework));
                if (groups.Length > 0 && nearest == null) throw new InvalidDataException("No compatible dependencies for " + identity);
                var dependencies = nearest == null ? new Dictionary<string, VersionRange>(StringComparer.OrdinalIgnoreCase) :
                    groups.Single(x => x.TargetFramework.Equals(nearest)).Packages.ToDictionary(x => x.Id, x => x.VersionRange, StringComparer.OrdinalIgnoreCase);
                found = new Package { Directory = directory, Dependencies = dependencies, Record = new LockedPackage {
                    Id = actual.Id, Version = version.ToNormalizedString(), Feed = selectedFeed ?? File.ReadAllText(origin), Hash = digest
                }};
                loaded.Add(identity, found); return found;
            }
            Dictionary<string, Package> selected;
            if (!UpdateLock && File.Exists(lockPath))
            {
                selected = new Dictionary<string, Package>(StringComparer.OrdinalIgnoreCase);
                foreach (var record in JsonSerializer.Deserialize<LockedPackage[]>(File.ReadAllBytes(lockPath)))
                    selected.Add(record.Id, Read(record.Id, NuGetVersion.Parse(record.Version), record.Feed, record.Hash));
                foreach (var root in roots)
                    if (!selected.TryGetValue(root.Key, out var package) || NuGetVersion.Parse(package.Record.Version) != root.Value)
                        throw new InvalidDataException("Dependency lock does not match root requests");
                Validate(selected);
            }
            else
            {
                var initial = roots.ToDictionary(x => x.Key, x => Read(x.Key, x.Value), StringComparer.OrdinalIgnoreCase);
                var versions = new Dictionary<string, NuGetVersion[]>(StringComparer.OrdinalIgnoreCase);
                NuGetVersion[] Versions(string id)
                {
                    if (versions.TryGetValue(id, out var known)) return known;
                    var available = new HashSet<NuGetVersion>();
                    var folder = Path.Combine(cache, "packages", id.ToLowerInvariant());
                    if (Directory.Exists(folder)) foreach (var child in Directory.GetDirectories(folder))
                        if (NuGetVersion.TryParse(Path.GetFileName(child), out var version)) available.Add(version);
                    foreach (var feed in sources)
                    {
                        if (Offline && Uri.TryCreate(feed, UriKind.Absolute, out var uri) && !uri.IsFile) continue;
                        foreach (var version in Resource(feed).GetAllVersionsAsync(id, sourceCache, NullLogger.Instance, cancellation).GetAwaiter().GetResult()) available.Add(version);
                    }
                    known = available.OrderBy(x => x).ToArray(); versions.Add(id, known); return known;
                }
                Dictionary<string, Package> Solve(Dictionary<string, Package> candidates)
                {
                    cancellation.ThrowIfCancellationRequested();
                    var requirements = new Dictionary<string, List<VersionRange>>(StringComparer.OrdinalIgnoreCase);
                    foreach (var package in candidates.Values) foreach (var dependency in package.Dependencies)
                    {
                        if (!requirements.TryGetValue(dependency.Key, out var ranges)) requirements.Add(dependency.Key, ranges = new List<VersionRange>());
                        ranges.Add(dependency.Value);
                    }
                    foreach (var entry in requirements)
                        if (candidates.TryGetValue(entry.Key, out var existing) && !entry.Value.All(x => x.Satisfies(NuGetVersion.Parse(existing.Record.Version)))) return null;
                    var missing = requirements.Keys.FirstOrDefault(x => !candidates.ContainsKey(x));
                    if (missing == null) return candidates;
                    foreach (var version in Versions(missing).Where(v => requirements[missing].All(r => r.Satisfies(v))))
                    {
                        var branch = new Dictionary<string, Package>(candidates, StringComparer.OrdinalIgnoreCase) { [missing] = Read(missing, version) };
                        var result = Solve(branch); if (result != null) return result;
                    }
                    return null;
                }
                selected = Solve(initial) ?? throw new InvalidDataException("No compatible package dependency graph");
            }
            var resolution = new ScriptResolution();
            foreach (var package in selected.Values.OrderBy(x => x.Record.Id, StringComparer.OrdinalIgnoreCase)) SelectAssets(package, framework, definition.RuntimeIdentifier, resolution);
            var records = selected.Values.Select(x => x.Record).OrderBy(x => x.Id, StringComparer.OrdinalIgnoreCase).ToArray();
            var lockBytes = JsonSerializer.SerializeToUtf8Bytes(records);
            resolution.LockFingerprint = Hash(lockBytes);
            if (UpdateLock || !File.Exists(lockPath))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(lockPath));
                var pending = lockPath + ".pending-" + Guid.NewGuid().ToString("N");
                try { File.WriteAllBytes(pending, lockBytes); File.Move(pending, lockPath, true); }
                finally { if (File.Exists(pending)) File.Delete(pending); }
            }
            return resolution;
        }
        static void Validate(Dictionary<string, Package> selected)
        {
            foreach (var package in selected.Values) foreach (var dependency in package.Dependencies)
                if (!selected.TryGetValue(dependency.Key, out var target) || !dependency.Value.Satisfies(NuGetVersion.Parse(target.Record.Version)))
                    throw new InvalidDataException("Invalid locked dependency: " + dependency.Key);
        }
        static IEnumerable<string> RuntimeFallbacks(string rid, string packageDirectory)
        {
            var graph = new Dictionary<string, string[]>(StringComparer.Ordinal);
            foreach (var path in new[] { Path.Combine(Path.GetDirectoryName(typeof(NuGetScriptResolver).Assembly.Location), "NuGet.RuntimeGraph.json"), Path.Combine(packageDirectory, "runtime.json") })
            {
                if (!File.Exists(path)) continue;
                using var document = JsonDocument.Parse(File.ReadAllBytes(path));
                if (!document.RootElement.TryGetProperty("runtimes", out var runtimes)) continue;
                foreach (var runtime in runtimes.EnumerateObject())
                    if (runtime.Value.TryGetProperty("#import", out var imports))
                        graph[runtime.Name] = imports.EnumerateArray().Select(x => x.GetString()).ToArray();
            }
            var queue = new Queue<string>(); var seen = new HashSet<string>(StringComparer.Ordinal);
            queue.Enqueue(rid);
            while (queue.Count > 0)
            {
                var current = queue.Dequeue(); if (!seen.Add(current)) continue;
                yield return current;
                if (graph.TryGetValue(current, out var parents)) foreach (var parent in parents) queue.Enqueue(parent);
            }
        }
        static void SelectAssets(Package package, NuGetFramework framework, string rid, ScriptResolution result)
        {
            using var reader = new PackageArchiveReader(Path.Combine(package.Directory, "package.nupkg"));
            string VerifiedAsset(string file)
            {
                var relative = file.Replace(Path.DirectorySeparatorChar, '/');
                var path = Path.Combine(package.Directory, file);
                using var original = reader.GetStream(relative);
                using var extracted = File.OpenRead(path);
                if (!SHA256.HashData(original).SequenceEqual(SHA256.HashData(extracted)))
                    throw new InvalidDataException("Cached package asset changed: " + package.Record.Id + "/" + relative);
                return path;
            }
            if (File.Exists(Path.Combine(package.Directory, "runtime.json"))) VerifiedAsset("runtime.json");
            IEnumerable<string> Nearest(IEnumerable<FrameworkSpecificGroup> groups)
            {
                var all = groups.ToArray(); var nearest = new FrameworkReducer().GetNearest(framework, all.Select(x => x.TargetFramework));
                return nearest == null ? Array.Empty<string>() : all.Single(x => x.TargetFramework.Equals(nearest)).Items;
            }
            var lib = Nearest(reader.GetLibItems()).Where(x => x.EndsWith(".dll", StringComparison.OrdinalIgnoreCase)).ToArray();
            var references = Nearest(reader.GetReferenceItems()).Where(x => x.EndsWith(".dll", StringComparison.OrdinalIgnoreCase)).ToArray();
            if (references.Length == 0) references = lib;
            var runtimeIds = RuntimeFallbacks(rid, package.Directory).ToArray();
            var runtimeRoots = runtimeIds.Select(x => Path.Combine(package.Directory, "runtimes", x)).Where(Directory.Exists).ToArray();
            var runtimeRoot = runtimeRoots.FirstOrDefault(x => Directory.Exists(Path.Combine(x, "lib")));
            if (runtimeRoot != null)
            {
                var runtimeLib = Path.Combine(runtimeRoot, "lib");
                if (Directory.Exists(runtimeLib))
                {
                    var folders = Directory.GetDirectories(runtimeLib);
                    var nearest = new FrameworkReducer().GetNearest(framework, folders.Select(x => NuGetFramework.ParseFolder(Path.GetFileName(x))));
                    if (nearest != null) lib = Directory.GetFiles(folders.Single(x => NuGetFramework.ParseFolder(Path.GetFileName(x)).Equals(nearest)), "*.dll").Select(x => Path.GetRelativePath(package.Directory, x)).ToArray();
                }
            }
            var native = runtimeRoots.Select(x => Path.Combine(x, "native")).FirstOrDefault(Directory.Exists);
            if (native == null && Directory.Exists(Path.Combine(package.Directory, "runtimes")) &&
                Directory.GetDirectories(Path.Combine(package.Directory, "runtimes")).Any(x => Directory.Exists(Path.Combine(x, "native"))))
                throw new InvalidDataException("No compatible native assets for " + package.Record.Id + " on " + rid);
            if (references.Length == 0) references = lib;
            if (native != null) foreach (var file in Directory.GetFiles(native, "*", SearchOption.AllDirectories)) result.NativeReferences.Add(VerifiedAsset(Path.GetRelativePath(package.Directory, file)));
            foreach (var file in references) result.CompilationReferences.Add(VerifiedAsset(file));
            foreach (var file in lib) result.RuntimeReferences.Add(VerifiedAsset(file));
            if (references.Length > 0 && lib.Length == 0) throw new InvalidDataException("Package has no executable managed assets: " + package.Record.Id);
        }
    }
}
