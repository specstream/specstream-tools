package ai.specstream.automationanywhere;

import static com.automationanywhere.commandsdk.model.AttributeType.CHECKBOX;
import static com.automationanywhere.commandsdk.model.AttributeType.CREDENTIAL;
import static com.automationanywhere.commandsdk.model.AttributeType.TEXT;

import com.automationanywhere.botcommand.data.Value;
import com.automationanywhere.botcommand.data.impl.DictionaryValue;
import com.automationanywhere.botcommand.data.impl.StringValue;
import com.automationanywhere.botcommand.exception.BotCommandException;
import com.automationanywhere.commandsdk.annotations.BotCommand;
import com.automationanywhere.commandsdk.annotations.CommandPkg;
import com.automationanywhere.commandsdk.annotations.Execute;
import com.automationanywhere.commandsdk.annotations.Idx;
import com.automationanywhere.commandsdk.annotations.Pkg;
import com.automationanywhere.commandsdk.annotations.rules.NotEmpty;
import com.automationanywhere.commandsdk.model.DataType;
import com.automationanywhere.core.security.SecureString;
import java.util.LinkedHashMap;
import java.util.Map;

@BotCommand
@CommandPkg(
    name = "webSearch",
    label = "[[WebSearch.label]]",
    node_label = "[[WebSearch.node_label]]",
    description = "[[WebSearch.description]]",
    icon = "specstream.svg",
    return_label = "[[WebSearch.return_label]]",
    return_description = "[[WebSearch.return_description]]",
    return_type = DataType.DICTIONARY,
    return_sub_type = DataType.STRING,
    return_required = true)
public class WebSearch {

  @Execute
  public DictionaryValue search(
      @Idx(index = "1", type = CREDENTIAL)
          @Pkg(label = "[[apiKey.label]]", description = "[[apiKey.description]]")
          @NotEmpty
          SecureString apiKey,
      @Idx(index = "2", type = TEXT) @Pkg(label = "[[WebSearch.question.label]]") @NotEmpty
          String question,
      @Idx(index = "3", type = CHECKBOX)
          @Pkg(
              label = "[[WebSearch.fast.label]]",
              description = "[[WebSearch.fast.description]]",
              default_value = "false",
              default_value_type = DataType.BOOLEAN)
          Boolean fast) {
    try {
      Map<String, String> found =
          new SpecStream(apiKey.getInsecureString()).search(question, Boolean.TRUE.equals(fast));
      Map<String, Value> out = new LinkedHashMap<>();
      for (Map.Entry<String, String> entry : found.entrySet()) {
        out.put(entry.getKey(), new StringValue(entry.getValue()));
      }
      return new DictionaryValue(out);
    } catch (IllegalArgumentException | IllegalStateException error) {
      throw new BotCommandException(error.getMessage());
    }
  }
}
