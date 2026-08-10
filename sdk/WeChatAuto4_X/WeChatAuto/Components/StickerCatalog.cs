using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.IO;
using System.Text;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Definitions;
using FlaUI.Core.Input;
using FlaUI.UIA3;
using Newtonsoft.Json;
using WeChatAuto.Extentions;
using WeChatAuto.Utils;
using WeAutoCommon.Utils;
using WeAutoCommon.Extentions;

namespace WeChatAuto.Components
{
    /// <summary>One entry in the locally scanned WeChat emoticon catalog.</summary>
    public sealed class StickerCatalogItem
    {
        public string Id { get; set; } = "";
        public string Category { get; set; } = "";
        public string Name { get; set; } = "";
        public string Mode { get; set; } = "semantic";
        public string Hash { get; set; } = "";
        public int Page { get; set; }
        public int Row { get; set; }
        public int Column { get; set; }
    }

    /// <summary>Result returned by ScanAllStickers.</summary>
    public sealed class StickerCatalogScanResult
    {
        public int Total { get; set; }
        public int Categories { get; set; }
        public int SemanticItems { get; set; }
        public int VisualItems { get; set; }
        public List<StickerCatalogItem> Items { get; set; } = new();
    }

    internal sealed class StickerCatalogStore
    {
        private const int MaxPages = 40;
        private const int MaxItems = 2000;
        private const int HashWidth = 9;
        private const int HashHeight = 8;
        private readonly string _path = Path.Combine(
            AppContext.BaseDirectory, "sticker-catalog", "manifest.json");

        public List<StickerCatalogItem> Items { get; private set; } = new();

        public StickerCatalogStore()
        {
            try
            {
                if (File.Exists(_path))
                    Items = JsonConvert.DeserializeObject<List<StickerCatalogItem>>(
                        File.ReadAllText(_path, Encoding.UTF8)) ?? new();
            }
            catch
            {
                Items = new();
            }
        }

        public void Replace(IEnumerable<StickerCatalogItem> items)
        {
            Items = items
                .GroupBy(x => x.Id, StringComparer.Ordinal)
                .Select(x => x.First())
                .Take(MaxItems)
                .ToList();
            Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
            var temp = _path + ".tmp";
            File.WriteAllText(temp, JsonConvert.SerializeObject(Items, Formatting.Indented), Encoding.UTF8);
            File.Move(temp, _path, true);
        }

        public static string DHash(Bitmap source)
        {
            using var resized = new Bitmap(HashWidth, HashHeight);
            using (var graphics = Graphics.FromImage(resized))
            {
                graphics.Clear(Color.Black);
                graphics.DrawImage(source, 0, 0, HashWidth, HashHeight);
            }
            var bits = new StringBuilder(HashWidth * HashHeight - HashHeight);
            for (var y = 0; y < HashHeight; y++)
            {
                for (var x = 0; x < HashWidth - 1; x++)
                {
                    var left = resized.GetPixel(x, y);
                    var right = resized.GetPixel(x + 1, y);
                    var leftGray = left.R * 299 + left.G * 587 + left.B * 114;
                    var rightGray = right.R * 299 + right.G * 587 + right.B * 114;
                    bits.Append(leftGray > rightGray ? '1' : '0');
                }
            }
            return Convert.ToInt64(bits.ToString(), 2).ToString("X16");
        }

        public static int Distance(string left, string right)
        {
            if (string.IsNullOrWhiteSpace(left) || string.IsNullOrWhiteSpace(right))
                return int.MaxValue;
            if (!long.TryParse(left, System.Globalization.NumberStyles.HexNumber, null, out var a)
                || !long.TryParse(right, System.Globalization.NumberStyles.HexNumber, null, out var b))
                return int.MaxValue;
            var value = (ulong)(a ^ b);
            var count = 0;
            while (value != 0) { count += (int)(value & 1); value >>= 1; }
            return count;
        }

        public static AutomationElement[] FindTabs(AutomationElement root)
        {
            return root.FindAllDescendants(cf => cf.ByClassName("mmui::EmoticonToolbarItem"))
                .Where(x => !string.IsNullOrWhiteSpace(x.Name) && !x.IsOffscreen
                    && !x.Name.Trim().Equals("搜索表情", StringComparison.Ordinal))
                .GroupBy(x => x.Name, StringComparer.Ordinal)
                .Select(x => x.First())
                .ToArray();
        }

        public static AutomationElement FindPanel(AutomationElement root)
        {
            return root.FindFirstDescendant(cf => cf.ByClassName("mmui::EmoticonContentView")) ?? root;
        }

        public static AutomationElement[] FindVisualCells(AutomationElement root)
        {
            var candidates = new List<AutomationElement>();
            foreach (var className in new[] {
                "mmui::EmoticonCell", "mmui::FavEmoticonItemView", "mmui::EmoticonItemView",
                "mmui::EmoticonItem", "mmui::StickerItemView"
            })
                candidates.AddRange(root.FindAllDescendants(cf => cf.ByClassName(className)));
            candidates.AddRange(root.FindAllDescendants(cf => cf.ByControlType(ControlType.Text))
                .Where(x => (x.ClassName ?? "").Contains("Emoticon", StringComparison.OrdinalIgnoreCase)));
            candidates = candidates
                .Where(x => !x.IsOffscreen && x.BoundingRectangle.Width >= 20 && x.BoundingRectangle.Height >= 20)
                .ToList();
            return candidates
                .GroupBy(x => (x.BoundingRectangle.X, x.BoundingRectangle.Y,
                    x.BoundingRectangle.Width, x.BoundingRectangle.Height))
                .Select(x => x.First())
                .OrderBy(x => x.BoundingRectangle.Y)
                .ThenBy(x => x.BoundingRectangle.X)
                .ToArray();
        }

        public static AutomationElement[] FindSemanticCells(AutomationElement root)
        {
            var blockedNames = new HashSet<string>(new[] {
                "搜索表情", "默认表情", "自定义表情", "发送表情(Alt+E)"
            }, StringComparer.Ordinal);
            var candidates = root.FindAllDescendants(cf => cf.ByControlType(ControlType.Text))
                .Where(x => !x.IsOffscreen && !string.IsNullOrWhiteSpace(x.Name))
                .Where(x => !blockedNames.Contains(x.Name.Trim()))
                .Where(x => x.BoundingRectangle.Width >= 10 && x.BoundingRectangle.Height >= 10);
            var itemViews = candidates
                .Where(x => (x.ClassName ?? "").Contains("EmoticonItemView", StringComparison.OrdinalIgnoreCase))
                .ToArray();
            if (itemViews.Length > 0)
                candidates = itemViews;
            return candidates
                .GroupBy(x => (x.Name.Trim(), x.BoundingRectangle.X, x.BoundingRectangle.Y))
                .Select(x => x.First())
                .OrderBy(x => x.BoundingRectangle.Y)
                .ThenBy(x => x.BoundingRectangle.X)
                .ToArray();
        }

        public StickerCatalogScanResult ScanAll(AutomationElement root, Window mainWindow)
        {
            var tabs = FindTabs(root);
            if (tabs.Length == 0)
                throw new InvalidOperationException("微信表情面板中没有发现可扫描的分类标签。");
            var items = new List<StickerCatalogItem>();
            foreach (var tab in tabs)
            {
                tab.ClickEnhance(mainWindow);
                RandomWait.Wait(150, 300);
                var panel = FindPanel(root);
                ScrollToStart(panel);
                var isVisual = tab.Name.Contains("自定义", StringComparison.Ordinal);
                var seenPages = new HashSet<string>(StringComparer.Ordinal);
                for (var page = 0; page < MaxPages && items.Count < MaxItems; page++)
                {
                    var cells = isVisual ? FindVisualCells(panel) : FindSemanticCells(panel);
                    if (cells.Length == 0)
                        break;
                    var pageSignature = string.Join("|", cells.Select(x => isVisual
                        ? HashOf(x)
                        : x.Name.Trim()));
                    if (!seenPages.Add(pageSignature))
                        break;
                    var columns = EstimateColumns(cells);
                    for (var index = 0; index < cells.Length; index++)
                    {
                        var cell = cells[index];
                        var hash = isVisual ? HashOf(cell) : "";
                        var name = isVisual ? "" : cell.Name.Trim();
                        var id = isVisual
                            ? $"visual:{tab.Name}:{hash}"
                            : $"semantic:{tab.Name}:{name}:{page}:{index % columns}";
                        items.Add(new StickerCatalogItem {
                            Id = id, Category = tab.Name.Trim(), Name = name,
                            Mode = isVisual ? "visual" : "semantic", Hash = hash,
                            Page = page, Row = index / columns, Column = index % columns
                        });
                    }
                    ScrollPanel(root, cells);
                }
            }
            Replace(items);
            return new StickerCatalogScanResult {
                Total = Items.Count,
                Categories = Items.Select(x => x.Category).Distinct(StringComparer.Ordinal).Count(),
                SemanticItems = Items.Count(x => x.Mode == "semantic"),
                VisualItems = Items.Count(x => x.Mode == "visual"),
                Items = Items
            };
        }

        public StickerCatalogItem Resolve(string category, string nameOrHash)
        {
            var value = nameOrHash.Trim();
            return Items.FirstOrDefault(x =>
                x.Category.Equals(category.Trim(), StringComparison.Ordinal)
                && ((x.Mode == "semantic" && x.Name.Equals(value, StringComparison.OrdinalIgnoreCase))
                    || (x.Mode == "visual" && x.Hash.Equals(value, StringComparison.OrdinalIgnoreCase))));
        }

        private static int EstimateColumns(IReadOnlyList<AutomationElement> cells)
        {
            if (cells.Count < 2) return 1;
            var top = cells[0].BoundingRectangle.Y;
            var count = cells.TakeWhile(x => Math.Abs(x.BoundingRectangle.Y - top) < 12).Count();
            return Math.Max(1, count);
        }

        private static string HashOf(AutomationElement element)
        {
            using var bitmap = element.Capture();
            return bitmap == null ? "" : DHash(bitmap);
        }

        private static void ScrollPanel(AutomationElement root, IReadOnlyList<AutomationElement> cells)
        {
            var target = cells.FirstOrDefault()?.GetParent() ?? root;
            var rect = target.BoundingRectangle;
            if (rect.IsEmpty) return;
            Mouse.Position = new Point(rect.X + rect.Width / 2, rect.Y + rect.Height / 2);
            Mouse.Scroll(-6);
            RandomWait.Wait(120, 250);
        }

        public static void ScrollToStart(AutomationElement root)
        {
            var rect = root.BoundingRectangle;
            if (rect.IsEmpty) return;
            Mouse.Position = new Point(rect.X + rect.Width / 2, rect.Y + rect.Height / 2);
            for (var index = 0; index < 12; index++)
            {
                Mouse.Scroll(12);
                RandomWait.Wait(20, 45);
            }
            RandomWait.Wait(120, 220);
        }
    }
}
