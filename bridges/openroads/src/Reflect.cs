using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;

namespace Bimai.OpenRoads
{
    /// <summary>
    /// Late-bound access to Bentley's civil API (CifNET). The bridge compiles against nothing but Bentley's
    /// AddIn base class; every civil call goes through here, so a member that is named differently in some
    /// OpenRoads version fails one value or one tool with a clear message instead of the whole build.
    /// </summary>
    public static class Reflect
    {
        private const BindingFlags Instance = BindingFlags.Public | BindingFlags.Instance;

        /// <summary>A type by full name from the loaded assemblies, else from assemblies with one of these names.</summary>
        public static Type FindType(string fullName, params string[] assemblyPrefixes)
        {
            Type t = Loaded(fullName);
            if (t != null) return t;
            foreach (string file in CandidateFiles(assemblyPrefixes))
            {
                try
                {
                    // Load by name (the normal load context) so the types are the ones OpenRoads uses itself.
                    var assembly = Assembly.Load(AssemblyName.GetAssemblyName(file));
                    t = assembly.GetType(fullName, false);
                    if (t != null) return t;
                }
                catch (Exception) { }
            }
            return null;
        }

        private static Type Loaded(string fullName)
        {
            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                try
                {
                    var t = assembly.GetType(fullName, false);
                    if (t != null) return t;
                }
                catch (Exception) { }
            }
            return null;
        }

        private static IEnumerable<string> CandidateFiles(string[] prefixes)
        {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            var folders = new List<string> { root };
            foreach (string sub in new[] { "Cif", "Civil" })
            {
                string folder = Path.Combine(root, sub);
                if (Directory.Exists(folder)) folders.Add(folder);
            }
            foreach (string folder in folders)
            {
                string[] files;
                try { files = Directory.GetFiles(folder, "*.dll"); }
                catch (Exception) { continue; }
                foreach (string file in files)
                {
                    string name = Path.GetFileName(file);
                    if (prefixes.Any(p => name.StartsWith(p, StringComparison.OrdinalIgnoreCase))) yield return file;
                }
            }
        }

        public static object GetStatic(Type type, string name)
        {
            var p = type.GetProperty(name, BindingFlags.Public | BindingFlags.Static);
            if (p != null) return p.GetValue(null, null);
            var f = type.GetField(name, BindingFlags.Public | BindingFlags.Static);
            if (f != null) return f.GetValue(null);
            throw new MissingMemberException(type.FullName, name);
        }

        /// <summary>A property or field; throws MissingMemberException when the object has neither.</summary>
        public static object Get(object target, string name)
        {
            if (target == null) return null;
            var type = target.GetType();
            var p = type.GetProperty(name, Instance, null, null, Type.EmptyTypes, null);
            if (p != null) return p.GetValue(target, null);
            var f = type.GetField(name, Instance);
            if (f != null) return f.GetValue(target);
            throw new MissingMemberException(type.FullName, name);
        }

        /// <summary>The first of these members that exists and can be read, else null.</summary>
        public static object TryGet(object target, params string[] names)
        {
            if (target == null) return null;
            foreach (string name in names)
            {
                try { return Get(target, name); }
                catch (Exception) { }
            }
            return null;
        }

        public static bool Has(object target, string name)
        {
            if (target == null) return false;
            var type = target.GetType();
            return type.GetProperty(name, Instance, null, null, Type.EmptyTypes, null) != null || type.GetField(name, Instance) != null;
        }

        /// <summary>Calls a public instance method by name with these arguments (the first overload that fits).</summary>
        public static object Call(object target, string name, params object[] args)
        {
            if (target == null) throw new ArgumentNullException("target", "can't call " + name + " on nothing");
            var method = FindMethod(target.GetType(), name, args);
            if (method == null) throw new MissingMethodException(target.GetType().FullName, name);
            return method.Invoke(target, args);
        }

        /// <summary>Calls a method without arguments; null when the object is null, lacks it, or it fails.</summary>
        public static object TryCallSafe(object target, string name)
        {
            if (target == null) return null;
            try { return Call(target, name); }
            catch (Exception) { return null; }
        }

        public static object CallStatic(Type type, string name, params object[] args)
        {
            var method = type.GetMethods(BindingFlags.Public | BindingFlags.Static)
                             .FirstOrDefault(m => m.Name == name && Fits(m, args));
            if (method == null) throw new MissingMethodException(type.FullName, name);
            return method.Invoke(null, args);
        }

        public static MethodInfo FindMethod(Type type, string name, object[] args)
        {
            return type.GetMethods(Instance).FirstOrDefault(m => m.Name == name && Fits(m, args));
        }

        private static bool Fits(MethodInfo m, object[] args)
        {
            var ps = m.GetParameters();
            if (ps.Length != args.Length) return false;
            for (int i = 0; i < ps.Length; i++)
            {
                var pt = ps[i].ParameterType.IsByRef ? ps[i].ParameterType.GetElementType() : ps[i].ParameterType;
                if (args[i] == null) { if (pt.IsValueType) return false; continue; }
                if (!pt.IsInstanceOfType(args[i])) return false;
            }
            return true;
        }

        public static IEnumerable<object> Items(object enumerable)
        {
            var e = enumerable as IEnumerable;
            if (e == null || enumerable is string) yield break;
            foreach (object item in e) yield return item;
        }

        public static double? Number(object value)
        {
            if (value == null) return null;
            if (value is double || value is float || value is int || value is long || value is short || value is decimal || value is uint)
            {
                double d = Convert.ToDouble(value, CultureInfo.InvariantCulture);
                return double.IsNaN(d) || double.IsInfinity(d) ? (double?)null : Math.Round(d, 6);
            }
            return null;
        }

        public static string Text(object value)
        {
            if (value == null) return null;
            var s = value as string;
            if (s != null) return s;
            var name = TryGet(value, "Name");
            return name != null ? Convert.ToString(name, CultureInfo.InvariantCulture) : Convert.ToString(value, CultureInfo.InvariantCulture);
        }

        /// <summary>
        /// The object's simple public properties (text, numbers, yes/no, enums), so the tester and the AI see
        /// what OpenRoads offers even where the bridge doesn't know the member names yet.
        /// </summary>
        public static Dictionary<string, object> Describe(object target, int max)
        {
            var result = Json.Obj();
            if (target == null) return result;
            foreach (var p in target.GetType().GetProperties(Instance).OrderBy(p => p.Name, StringComparer.Ordinal))
            {
                if (result.Count >= max) break;
                if (p.GetIndexParameters().Length > 0 || !p.CanRead) continue;
                var t = Nullable.GetUnderlyingType(p.PropertyType) ?? p.PropertyType;
                bool simple = t == typeof(string) || t == typeof(bool) || t.IsEnum || t == typeof(double) || t == typeof(float)
                              || t == typeof(int) || t == typeof(long) || t == typeof(short) || t == typeof(uint) || t == typeof(Guid);
                if (!simple) continue;
                try
                {
                    object v = p.GetValue(target, null);
                    if (v == null) continue;
                    if (t.IsEnum || t == typeof(Guid)) v = v.ToString();
                    else if (t != typeof(string) && t != typeof(bool)) v = Number(v);
                    if (v != null) result[p.Name] = v;
                }
                catch (Exception) { }
            }
            return result;
        }
    }
}
