/* A local disk cache for fast lookups of NAR index files in a binary
   cache. */

#include "binary-cache-store.hh"
#include "fs-accessor.hh"
#include "sqlite.hh"
#include "sync.hh"

#include <sqlite3.h>
#include <nlohmann/json.hpp>

using namespace nix;

MakeError(BadJSON, Error);

class FileCache
{
    struct State
    {
        SQLite db;
        SQLiteStmt queryPath, insertPath, queryFiles, insertFile;
    };

    Sync<State> state_;

    struct Stat : FSAccessor::Stat
    {
        std::string target;
    };

public:

    FileCache(const Path & path)
    {
        auto state(state_.lock());

        static std::string cacheSchema = R"sql(

          create table if not exists StorePaths (
            id   integer primary key autoincrement not null,
            path text unique not null
          );

          create table if not exists StorePathContents (
            storePath integer not null,
            subPath text not null,
            type integer not null,
            fileSize integer,
            isExecutable integer,
            target text,
            primary key (storePath, subPath),
            foreign key (storePath) references StorePaths(id) on delete cascade
          );

        )sql";

        state->db = SQLite(path);
        state->db.exec("pragma foreign_keys = 1");
        state->db.exec(cacheSchema);

        if (sqlite3_busy_timeout(state->db, 60 * 60 * 1000) != SQLITE_OK)
            throwSQLiteError(state->db, "setting timeout");

        state->queryPath.create(state->db,
            "select id from StorePaths where path = ?");
        state->insertPath.create(state->db,
            "insert or ignore into StorePaths(path) values (?)");
        state->queryFiles.create(state->db,
            "select subPath, type, fileSize, isExecutable, target from StorePathContents where storePath = ?");
        state->insertFile.create(state->db,
            "insert into StorePathContents(storePath, subPath, type, fileSize, isExecutable, target) values (?, ?, ?, ?, ?, ?)");
    }

    /* Return the files in a store path, using a SQLite database to
       cache the results. */
    std::map<std::string, Stat>
    getFiles(ref<BinaryCacheStore> binaryCache, const Path & storePath)
    {
        std::map<std::string, Stat> files;

        /* Look up the path in the SQLite cache. */
        {
            auto state(state_.lock());
            auto useQueryPath(state->queryPath.use()(storePath));
            if (useQueryPath.next()) {
                auto id = useQueryPath.getInt(0);
                auto useQueryFiles(state->queryFiles.use()(id));
                while (useQueryFiles.next()) {
                    Stat st;
                    st.type = (FSAccessor::Type) useQueryFiles.getInt(1);
                    st.fileSize = (uint64_t) useQueryFiles.getInt(2);
                    st.isExecutable = useQueryFiles.getInt(3) != 0;
                    if (!useQueryFiles.isNull(4))
                        st.target = useQueryFiles.getStr(4);
                    files.emplace(useQueryFiles.getStr(0), st);
                }
                return files;
            }
        }

        using json = nlohmann::json;

        std::function<void(const std::string &, json &)> recurse;

        recurse = [&](const std::string & relPath, json & v) {
            Stat st;

            std::string type = v["type"];

            if (type == "directory") {
                st.type = FSAccessor::Type::tDirectory;
                for (auto i = v["entries"].begin(); i != v["entries"].end(); ++i) {
                    std::string name = i.key();
                    recurse(relPath.empty() ? name : relPath + "/" + name, i.value());
                }
            } else if (type == "regular") {
                st.type = FSAccessor::Type::tRegular;
                st.fileSize = v["size"];
                st.isExecutable = v.value("executable", false);
            } else if (type == "symlink") {
                st.type = FSAccessor::Type::tSymlink;
                st.target = v.value("target", "");
            } else return;

            files[relPath] = st;
        };

        /* It's not in the cache, so get the .ls.xz file (which
           contains a JSON serialisation of the listing of the NAR
           contents) from the binary cache. */
        auto now1 = std::chrono::steady_clock::now();
        auto s = binaryCache->getFile(storePathToHash(storePath) + ".ls");
        if (!s)
            printInfo("warning: no listing of %s in binary cache", storePath);
        else {
            try {
                json ls = json::parse(*s);

                if (ls.value("version", 0) != 1)
                    throw Error("NAR index for ‘%s’ has an unsupported version", storePath);

                recurse("", ls.at("root"));
            } catch (std::invalid_argument & e) {
                // FIXME: some filenames have non-UTF8 characters in them,
                // which is not supported by nlohmann::json. So we have to
                // skip the entire package.
                throw BadJSON(e.what());
            }
        }

        /* Insert the store path into the database. */
        {
            auto state(state_.lock());
            SQLiteTxn txn(state->db);

            if (state->queryPath.use()(storePath).next()) return files;
            state->insertPath.use()(storePath).exec();
            uint64_t id = sqlite3_last_insert_rowid(state->db);

            for (auto & x : files) {
                state->insertFile.use()
                    (id)
                    (x.first)
                    (x.second.type)
                    (x.second.fileSize, x.second.type == FSAccessor::Type::tRegular)
                    (x.second.isExecutable, x.second.type == FSAccessor::Type::tRegular)
                    (x.second.target, x.second.type == FSAccessor::Type::tSymlink)
                    .exec();
            }

            txn.commit();
        }

        auto now2 = std::chrono::steady_clock::now();
        printInfo("processed %s in %d ms", storePath,
            std::chrono::duration_cast<std::chrono::milliseconds>(now2 - now1).count());

        return files;
    }
};

