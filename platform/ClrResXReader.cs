using System;
using System.Collections;
using System.ComponentModel;
using System.Text;
using System.Globalization;
using System.IO;
using System.Xml;

namespace Nemerle.Platform
{
    // Portable resource metadata used by the Resource macro. No WinForms and
    // no legacy binary object deserialization; unsupported values fail clearly.
    public sealed class ClrResXReader : IEnumerable, IDisposable
    {
        readonly Hashtable values = new Hashtable();
        public ClrResXReader(TextReader input) : this(input, Directory.GetCurrentDirectory()) { }
        public ClrResXReader(TextReader input, string baseDirectory)
        {
            var document = new XmlDocument { XmlResolver = null };
            document.Load(input);
            foreach (XmlElement data in document.SelectNodes("/root/data"))
            {
                string name = data.GetAttribute("name");
                var value = data.SelectSingleNode("value");
                if (value == null) throw new ArgumentException("Resource has no value: " + name);
                string typeName = data.GetAttribute("type");
                string mime = data.GetAttribute("mimetype");
                if (mime.Length != 0 && mime != "application/x-microsoft.net.object.bytearray.base64")
                    throw new NotSupportedException("Serialized object resources are not supported by the portable Resource macro: " + name);
                object result;
                if (mime == "application/x-microsoft.net.object.bytearray.base64")
                {
                    var type = Type.GetType(typeName, true);
                    var converter = TypeDescriptor.GetConverter(type);
                    if (type == typeof(byte[])) result = Convert.FromBase64String(value.InnerText);
                    else
                    {
                        if (!converter.CanConvertFrom(typeof(byte[])))
                            throw new NotSupportedException("Resource type has no byte-array converter: " + typeName);
                        result = converter.ConvertFrom(null, CultureInfo.InvariantCulture, Convert.FromBase64String(value.InnerText));
                    }
                }
                else if (typeName.Split(',')[0] == "System.Resources.ResXNullRef") result = null;
                else if (typeName.Length == 0 || typeName.Split(',')[0] == "System.String") result = value.InnerText;
                else if (typeName.Split(',')[0] == "System.Byte[]") result = Convert.FromBase64String(value.InnerText);
                else if (typeName.Split(',')[0] == "System.Resources.ResXFileRef")
                {
                    var parts = value.InnerText.Split(';');
                    if (parts.Length < 2) throw new ArgumentException("Invalid file resource: " + name);
                    string fileType = parts[1].Split(',')[0];
                    string path = Path.IsPathRooted(parts[0]) ? parts[0] : Path.Combine(baseDirectory, parts[0]);
                    if (fileType == "System.Byte[]") result = File.ReadAllBytes(path);
                    else if (fileType == "System.String") result = File.ReadAllText(path, parts.Length > 2 ? Encoding.GetEncoding(parts[2]) : Encoding.UTF8);
                    else throw new NotSupportedException("Unsupported file resource type: " + fileType);
                }
                else
                {
                    var type = Type.GetType(typeName, true);
                    var converter = TypeDescriptor.GetConverter(type);
                    if (!converter.CanConvertFrom(typeof(string)))
                        throw new NotSupportedException("Resource type has no string converter: " + typeName);
                    result = converter.ConvertFromInvariantString(value.InnerText);
                }
                values.Add(name, result);
            }
        }
        public IEnumerator GetEnumerator() { return values.GetEnumerator(); }
        public void Dispose() { }
    }
}
