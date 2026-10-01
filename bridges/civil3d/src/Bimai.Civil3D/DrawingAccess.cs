using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.Civil.ApplicationServices;
using Bimai.Mcp;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilEntity = Autodesk.Civil.DatabaseServices.Entity;

namespace Bimai.Civil3D;

/// <summary>Everything a tool may use while reading: the document, its database, an open transaction.</summary>
internal sealed class Reading
{
    public Document Document { get; }
    public Database Database { get; }
    public Transaction Transaction { get; }
    public CivilDocument Civil { get; }

    public Reading(Document document, Transaction transaction, CivilDocument civil)
    {
        Document = document;
        Database = document.Database;
        Transaction = transaction;
        Civil = civil;
    }

    /// <summary>Opens an object for reading only. The bridge never opens anything for write.</summary>
    public T Open<T>(ObjectId id) where T : DBObject => (T)Transaction.GetObject(id, OpenMode.ForRead);

    public IEnumerable<T> OpenAll<T>(IEnumerable<ObjectId> ids) where T : DBObject
    {
        foreach (var id in ids)
            if (!id.IsNull && !id.IsErased && Transaction.GetObject(id, OpenMode.ForRead) is T obj)
                yield return obj;
    }

    /// <summary>The name of a Civil 3D object (alignment, profile, structure, assembly…), or null.</summary>
    public string? NameOf(ObjectId id)
    {
        if (id.IsNull || id.IsErased) return null;
        return Transaction.GetObject(id, OpenMode.ForRead) switch
        {
            CivilEntity civil => civil.Name,
            SymbolTableRecord record => record.Name,
            _ => null,
        };
    }

    /// <summary>Finds a Civil 3D object by name (case-insensitive) or fails with the list of names.</summary>
    public T FindByName<T>(IEnumerable<ObjectId> ids, string name, string kind) where T : CivilEntity
    {
        var all = OpenAll<T>(ids).ToList();
        var match = all.FirstOrDefault(o => string.Equals(o.Name, name, StringComparison.OrdinalIgnoreCase));
        if (match is not null) return match;
        var names = all.Select(o => o.Name).OrderBy(n => n, StringComparer.OrdinalIgnoreCase).ToList();
        var listed = names.Count == 0 ? $"There are no {kind}s in this drawing."
            : $"{char.ToUpperInvariant(kind[0])}{kind[1..]}s in this drawing: {string.Join(", ", names.Take(50))}{(names.Count > 50 ? $" (and {names.Count - 50} more)" : "")}.";
        throw new ToolException($"No {kind} named '{name}'. {listed}");
    }
}

/// <summary>
/// The only way tools touch the drawing. Runs on the main thread (via the dispatcher) and:
/// refuses while a command, LISP or ARX command is active; locks the active document for reading without
/// prompting (Autodesk: locking fails instead when a command is in progress); reads inside a transaction.
/// </summary>
internal static class DrawingAccess
{
    public const string Busy = "Civil 3D is busy: a command is running. Finish or cancel it (press Esc) and try again.";
    public const string NoDrawing = "No drawing is open in Civil 3D. Open a drawing and try again.";

    public static T Read<T>(Func<Reading, T> work)
    {
        if (!AcApp.IsQuiescent) throw new ToolException(Busy);
        var document = AcApp.DocumentManager.MdiActiveDocument ?? throw new ToolException(NoDrawing);

        DocumentLock documentLock;
        try
        {
            documentLock = document.LockDocument(DocumentLockMode.Read, null, null, false);
        }
        catch (Autodesk.AutoCAD.Runtime.Exception)
        {
            throw new ToolException(Busy);
        }

        using (documentLock)
        {
            var civil = CivilApplication.ActiveDocument
                        ?? throw new ToolException("The active drawing is not available as a Civil 3D document.");
            using var transaction = document.Database.TransactionManager.StartOpenCloseTransaction();
            var result = work(new Reading(document, transaction, civil));
            transaction.Commit();
            return result;
        }
    }
}
