using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Drawing;
using MessagePack;
using Newtonsoft.Json;
using WeAutoCommon.Enums;

namespace WeChatAuto.Models
{
    [MessagePackObject]
    public class SimpleMessageBubble : IEquatable<SimpleMessageBubble>
    {
        /// <summary>
        /// 微信名
        /// 如果是自己发送，则值为"我"
        /// 如果是系统发送，则值为"系统"
        /// </summary>
        [Key(1)]
        [JsonProperty("who")]
        public string Who { get; set; }
        /// <summary>
        /// 消息
        /// </summary>
        [Key(2)]
        [JsonProperty("message")]
        public string Message { get; set; }
        /// <summary>
        /// 发送日期,仅精确到分钟
        /// </summary>
        [Key(3)]
        [JsonProperty("send_date")]
        public DateTime SendDate { get; set; }
        /// <summary>
        /// 如果消息中有图片，此处为图片的Bitmap对象，否则为null
        /// 注意：如果消息中有图片，且MessageMonitorOptions.FetchImage=false，则此处为null
        /// 注意：如果消息中有图片，且MessageMonitorOptions.FetchImage=true，则此处为Bitmap对象
        /// 注意：如果消息中有图片，且MessageMonitorOptions.FetchImage=true，但获取图片失败，则此处为null
        /// </summary>
        [IgnoreMember]
        public Bitmap Image { get; set; }

        /// <summary>
        /// 消息类型
        /// </summary>
        [Key(5)]
        [JsonProperty("message_type")]
        public MessageType MessageType { get; set; } = MessageType.None;

        /// <summary>
        /// 图片路径
        /// 如果消息中有图片，此处为图片的路径
        /// 注意：如果消息中有图片，且MessageMonitorOptions.FetchImage=false，则此处为null
        /// 注意：如果消息中有图片，且MessageMonitorOptions.FetchImage=true，则此处非空
        /// 注意：如果消息中有图片，且MessageMonitorOptions.FetchImage=true，但获取图片失败，则此处为null
        /// </summary>
        [Key(6)]
        public string ImageFile { get; set; }
        [IgnoreMember]
        [JsonProperty("image_base64_str")]
        public string ImageBase64Str { get; set; }

        [Key(7)]
        [JsonProperty("file_name")]
        public string FileName { get; set; }

        [Key(8)]
        [JsonProperty("file_path")]
        public string FilePath { get; set; }

        /// <summary>当前气泡是否为引用回复。</summary>
        [Key(9)]
        [JsonProperty("is_reference")]
        public bool IsReference { get; set; }

        /// <summary>被引用消息的发送者；微信未暴露时为空。</summary>
        [Key(10)]
        [JsonProperty("referenced_who")]
        public string ReferencedWho { get; set; }

        /// <summary>被引用的消息内容；微信未暴露时为空。</summary>
        [Key(11)]
        [JsonProperty("referenced_message")]
        public string ReferencedMessage { get; set; }

        public override string ToString()
        {
            return $"who={this.Who} Message={this.Message} SendDate={this.SendDate.ToString("yyyy-MM-dd HH:mm")} Image={(this.Image != null ? "有图片" : "无")} MessageType={this.MessageType.ToString()} ImageFile={this.ImageFile} IsReference={this.IsReference} ReferencedWho={this.ReferencedWho}";
        }
        /// <summary>
        /// 得到特征值
        /// </summary>
        /// <returns></returns>
        internal string GetFeature()
        {
            var date = SendDate;
            if (date == default)
            {
                return $"{Who}|{Message}|{MessageType.ToString()}|{IsReference}|{ReferencedWho}|{ReferencedMessage}";
            }
            else
            {
                return $"{Who}|{Message}|{date.ToString("yyyy-MM-dd HH:mm")}|{MessageType.ToString()}|{IsReference}|{ReferencedWho}|{ReferencedMessage}";
            }
        }

        public SimpleMessageBubble Clone()
        {
            return new SimpleMessageBubble
            {
                Who = this.Who,
                Message = this.Message,
                SendDate = this.SendDate,
                MessageType = this.MessageType,
                ImageFile = this.ImageFile,
                Image = this.Image,
                ImageBase64Str = this.ImageBase64Str,
                FileName = this.FileName,
                FilePath = this.FilePath,
                IsReference = this.IsReference,
                ReferencedWho = this.ReferencedWho,
                ReferencedMessage = this.ReferencedMessage,
            };
        }

        public override int GetHashCode()
        {
            return GetFeature().GetHashCode();
        }

        public bool Equals(SimpleMessageBubble other)
        {
            if (other == null)
                return false;
            return this.GetFeature().Equals(other.GetFeature());
        }

        public override bool Equals(object obj)
        {
            return Equals(obj as SimpleMessageBubble);
        }

    }
}
