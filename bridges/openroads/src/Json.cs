// bimai OpenRoads bridge. C# 5 on purpose: bimai compiles this file on the user's PC with the C# compiler
// that ships with Windows' .NET Framework 4.8, which supports C# 5 only.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Bimai.OpenRoads
{
    /// <summary>
    /// Minimal JSON: objects are Dictionary&lt;string, object&gt; (insertion order kept), arrays List&lt;object&gt;,
    /// strings, bool, null, and numbers as long (integers) or double. No dependencies, so nothing can clash
    /// with the assemblies OpenRoads Designer loads itself.
    /// </summary>
    public static class Json
    {
        public static Dictionary<string, object> Obj() { return new Dictionary<string, object>(); }

        public static object Parse(string text)
        {
            var p = new Parser(text);
            p.SkipSpace();
            var value = p.Value(0);
            p.SkipSpace();
            if (!p.AtEnd) throw new FormatException("unexpected text after the JSON value");
            return value;
        }

        public static string Write(object value)
        {
            var sb = new StringBuilder();
            WriteValue(sb, value, 0);
            return sb.ToString();
        }

        private static void WriteValue(StringBuilder sb, object value, int depth)
        {
            if (depth > 64) throw new InvalidOperationException("JSON nested too deeply");
            if (value == null) { sb.Append("null"); return; }
            var s = value as string;
            if (s != null) { WriteString(sb, s); return; }
            if (value is bool) { sb.Append((bool)value ? "true" : "false"); return; }
            if (value is double || value is float)
            {
                double d = Convert.ToDouble(value, CultureInfo.InvariantCulture);
                if (double.IsNaN(d) || double.IsInfinity(d)) sb.Append("null");
                else sb.Append(d.ToString("R", CultureInfo.InvariantCulture));
                return;
            }
            if (value is int || value is long || value is short || value is byte || value is uint || value is ulong || value is decimal)
            {
                sb.Append(Convert.ToString(value, CultureInfo.InvariantCulture));
                return;
            }
            var dict = value as IDictionary<string, object>;
            if (dict != null)
            {
                sb.Append('{');
                bool first = true;
                foreach (var kv in dict)
                {
                    if (!first) sb.Append(',');
                    first = false;
                    WriteString(sb, kv.Key);
                    sb.Append(':');
                    WriteValue(sb, kv.Value, depth + 1);
                }
                sb.Append('}');
                return;
            }
            var list = value as IEnumerable;
            if (list != null)
            {
                sb.Append('[');
                bool first = true;
                foreach (var item in list)
                {
                    if (!first) sb.Append(',');
                    first = false;
                    WriteValue(sb, item, depth + 1);
                }
                sb.Append(']');
                return;
            }
            WriteString(sb, Convert.ToString(value, CultureInfo.InvariantCulture));
        }

        private static void WriteString(StringBuilder sb, string s)
        {
            sb.Append('"');
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        else sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
        }

        // ------------------------------------------------------------------ typed access

        public static Dictionary<string, object> AsObject(object value)
        {
            return value as Dictionary<string, object>;
        }

        public static object Get(Dictionary<string, object> obj, string name)
        {
            object v;
            return obj != null && obj.TryGetValue(name, out v) ? v : null;
        }

        public static string GetString(Dictionary<string, object> obj, string name)
        {
            return Get(obj, name) as string;
        }

        private sealed class Parser
        {
            private readonly string _s;
            private int _i;

            public Parser(string s) { _s = s; }

            public bool AtEnd { get { return _i >= _s.Length; } }

            public void SkipSpace()
            {
                while (_i < _s.Length && (_s[_i] == ' ' || _s[_i] == '\t' || _s[_i] == '\n' || _s[_i] == '\r')) _i++;
            }

            private char Peek()
            {
                if (_i >= _s.Length) throw new FormatException("unexpected end of JSON");
                return _s[_i];
            }

            public object Value(int depth)
            {
                if (depth > 64) throw new FormatException("JSON nested too deeply");
                char c = Peek();
                if (c == '{') return ObjectValue(depth);
                if (c == '[') return ArrayValue(depth);
                if (c == '"') return StringValue();
                if (c == 't') { Expect("true"); return true; }
                if (c == 'f') { Expect("false"); return false; }
                if (c == 'n') { Expect("null"); return null; }
                if (c == '-' || (c >= '0' && c <= '9')) return NumberValue();
                throw new FormatException("unexpected character '" + c + "'");
            }

            private void Expect(string word)
            {
                if (string.CompareOrdinal(_s, _i, word, 0, word.Length) != 0) throw new FormatException("expected " + word);
                _i += word.Length;
            }

            private Dictionary<string, object> ObjectValue(int depth)
            {
                var result = new Dictionary<string, object>();
                _i++;
                SkipSpace();
                if (Peek() == '}') { _i++; return result; }
                while (true)
                {
                    SkipSpace();
                    if (Peek() != '"') throw new FormatException("expected a property name");
                    string key = StringValue();
                    SkipSpace();
                    if (Peek() != ':') throw new FormatException("expected ':'");
                    _i++;
                    SkipSpace();
                    result[key] = Value(depth + 1);
                    SkipSpace();
                    char c = Peek();
                    _i++;
                    if (c == '}') return result;
                    if (c != ',') throw new FormatException("expected ',' or '}'");
                }
            }

            private List<object> ArrayValue(int depth)
            {
                var result = new List<object>();
                _i++;
                SkipSpace();
                if (Peek() == ']') { _i++; return result; }
                while (true)
                {
                    SkipSpace();
                    result.Add(Value(depth + 1));
                    SkipSpace();
                    char c = Peek();
                    _i++;
                    if (c == ']') return result;
                    if (c != ',') throw new FormatException("expected ',' or ']'");
                }
            }

            private string StringValue()
            {
                _i++;
                var sb = new StringBuilder();
                while (true)
                {
                    char c = Peek();
                    _i++;
                    if (c == '"') return sb.ToString();
                    if (c < 0x20) throw new FormatException("control character in string");
                    if (c != '\\') { sb.Append(c); continue; }
                    char e = Peek();
                    _i++;
                    switch (e)
                    {
                        case '"': sb.Append('"'); break;
                        case '\\': sb.Append('\\'); break;
                        case '/': sb.Append('/'); break;
                        case 'b': sb.Append('\b'); break;
                        case 'f': sb.Append('\f'); break;
                        case 'n': sb.Append('\n'); break;
                        case 'r': sb.Append('\r'); break;
                        case 't': sb.Append('\t'); break;
                        case 'u':
                            if (_i + 4 > _s.Length) throw new FormatException("bad \\u escape");
                            sb.Append((char)int.Parse(_s.Substring(_i, 4), NumberStyles.HexNumber, CultureInfo.InvariantCulture));
                            _i += 4;
                            break;
                        default: throw new FormatException("bad escape");
                    }
                }
            }

            private object NumberValue()
            {
                int start = _i;
                if (_s[_i] == '-') _i++;
                while (_i < _s.Length && "0123456789+-.eE".IndexOf(_s[_i]) >= 0) _i++;
                string text = _s.Substring(start, _i - start);
                long l;
                if (text.IndexOfAny(new[] { '.', 'e', 'E' }) < 0 && long.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out l))
                    return l;
                double d;
                if (!double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out d)) throw new FormatException("bad number");
                return d;
            }
        }
    }
}
