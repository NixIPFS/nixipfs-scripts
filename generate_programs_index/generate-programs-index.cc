#include <nix/config.h>

#include <chrono>
#include <regex>

#include "shared.hh"
#include "globals.hh"
#include "eval.hh"
#include "store-api.hh"
#include "get-drvs.hh"
#include "thread-pool.hh"
#include "sqlite.hh"
#include "download.hh"
#include "binary-cache-store.hh"

#include "file-cache.hh"

using namespace nix;

static const char * programsSchema = R"sql(

  create table if not exists Programs (
    name        text not null,
    system      text not null,
    package     text not null,
    primary key (name, system, package)
  );

)sql";

void mainWrapped(int argc, char * * argv)
{
    initNix();
    initGC();

    if (argc != 6) throw Error("usage: generate-programs-index CACHE-DB PROGRAMS-DB BINARY-CACHE-URI STORE-PATHS NIXPKGS-PATH");

    Path cacheDbPath = argv[1];
    Path programsDbPath = argv[2];
    Path storePathsFile = argv[4];
    Path nixpkgsPath = argv[5];

    settings.readOnlyMode = true;
    settings.showTrace = true;

    auto localStore = openStore();
    std::string binaryCacheUri = argv[3];
    if (hasSuffix(binaryCacheUri, "/")) binaryCacheUri.pop_back();
    auto binaryCache = openStore(binaryCacheUri).cast<BinaryCacheStore>();

    /* Get the allowed store paths to be included in the database. */
    auto allowedPaths = tokenizeString<PathSet>(readFile(storePathsFile, true));

    PathSet allowedPathsClosure;
    binaryCache->computeFSClosure(allowedPaths, allowedPathsClosure);

    printMsg(lvlInfo, format("%d top-level paths, %d paths in closure")
        % allowedPaths.size() % allowedPathsClosure.size());

    FileCache fileCache(cacheDbPath);

    /* Initialise the programs database. */
    struct ProgramsState
    {
        SQLite db;
        SQLiteStmt insertProgram;
    };

    Sync<ProgramsState> programsState_;

    unlink(programsDbPath.c_str());

    {
        auto programsState(programsState_.lock());

        programsState->db = SQLite(programsDbPath);
        programsState->db.exec("pragma synchronous = off");
        programsState->db.exec("pragma main.journal_mode = truncate");
        programsState->db.exec(programsSchema);

        programsState->insertProgram.create(programsState->db,
            "insert or replace into Programs(name, system, package) values (?, ?, ?)");
    }

    EvalState state({}, localStore);

    Value vRoot;
    state.eval(state.parseExprFromFile(resolveExprPath(absPath(nixpkgsPath))), vRoot);

    /* Get all derivations. */
    DrvInfos packages;

    for (auto system : std::set<std::string>{"x86_64-linux", "i686-linux"}) {
        auto args = state.allocBindings(2);
        Value * vConfig = state.allocValue();
        state.mkAttrs(*vConfig, 0);
        args->push_back(Attr(state.symbols.create("config"), vConfig));
        Value * vSystem = state.allocValue();
        mkString(*vSystem, system);
        args->push_back(Attr(state.symbols.create("system"), vSystem));
        args->sort();
        getDerivations(state, vRoot, "", *args, packages, true);
    }

    /* For each store path, figure out the package with the shortest
       attribute name. E.g. "nix" is preferred over "nixStable". */
    std::map<Path, DrvInfo *> packagesByPath;

    for (auto & package : packages)
        try {
            auto outputs = package.queryOutputs(true);

            for (auto & output : outputs) {
                if (!allowedPathsClosure.count(output.second)) continue;
                auto i = packagesByPath.find(output.second);
                if (i != packagesByPath.end() &&
                    (i->second->attrPath.size() < package.attrPath.size() ||
                     (i->second->attrPath.size() == package.attrPath.size() && i->second->attrPath < package.attrPath)))
                    continue;
                packagesByPath[output.second] = &package;
            }
        } catch (AssertionError & e) {
        } catch (Error & e) {
            e.addPrefix(format("in package ‘%s’: ") % package.attrPath);
            throw;
        }

    /* Note: we don't index hidden files. */
    std::regex isProgram("bin/([^.][^/]*)");

    /* Process each store path. */
    auto doPath = [&](const Path & storePath, DrvInfo * package) {
        try {
            auto files = fileCache.getFiles(binaryCache, storePath);
            if (files.empty()) return;

            std::set<std::string> programs;

            for (auto file : files) {

                std::smatch match;
                if (!std::regex_match(file.first, match, isProgram)) continue;

                auto curPath = file.first;
                auto stat = file.second;

                while (stat.type == FSAccessor::Type::tSymlink) {

                    auto target = canonPath(
                        hasPrefix(stat.target, "/")
                        ? stat.target
                        : dirOf(storePath + "/" + curPath) + "/" + stat.target);
                    // FIXME: resolve symlinks in components of stat.target.

                    if (!hasPrefix(target, "/nix/store/")) break;

                    /* Assume that symlinks to other store paths point
                       to executables. But check symlinks within the
                       same store path. */
                    if (target.compare(0, storePath.size(), storePath) != 0) {
                        stat.type = FSAccessor::Type::tRegular;
                        stat.isExecutable = true;
                        break;
                    }

                    std::string sub(target, storePath.size() + 1);

                    auto file2 = files.find(sub);
                    if (file2 == files.end()) {
                        printError("symlink ‘%s’ has non-existent target ‘%s’",
                            storePath + "/" + file.first, stat.target);
                        break;
                    }

                    curPath = sub;
                    stat = file2->second;
                }

                if (stat.type == FSAccessor::Type::tDirectory
                    || stat.type == FSAccessor::Type::tSymlink
                    || (stat.type == FSAccessor::Type::tRegular && !stat.isExecutable))
                    continue;

                programs.insert(match[1]);
            }

            if (programs.empty()) return;

            {
                auto programsState(programsState_.lock());
                SQLiteTxn txn(programsState->db);
                for (auto & program : programs)
                    programsState->insertProgram.use()(program)(package->querySystem())(package->attrPath).exec();
                txn.commit();
            }

        } catch (BadJSON & e) {
            printError("error: in %s (%s): %s", package->attrPath, storePath, e.what());
        }
    };

    /* Enqueue work items for each package. */
    ThreadPool threadPool(16);

    for (auto & i : packagesByPath)
        threadPool.enqueue(std::bind(doPath, i.first, i.second));

    threadPool.process();

    /* Vacuum programs.sqlite to make it smaller. */
    {
        auto programsState(programsState_.lock());
        programsState->db.exec("vacuum");
    }
}

int main(int argc, char * * argv)
{
    return handleExceptions(argv[0], [&]() {
        mainWrapped(argc, argv);
    });
}
