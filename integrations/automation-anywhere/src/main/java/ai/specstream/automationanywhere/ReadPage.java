package ai.specstream.automationanywhere;

import static com.automationanywhere.commandsdk.model.AttributeType.CREDENTIAL;
import static com.automationanywhere.commandsdk.model.AttributeType.TEXT;

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

@BotCommand
@CommandPkg(
    name = "readPage",
    label = "[[ReadPage.label]]",
    node_label = "[[ReadPage.node_label]]",
    description = "[[ReadPage.description]]",
    icon = "specstream.svg",
    return_label = "[[ReadPage.return_label]]",
    return_description = "[[ReadPage.return_description]]",
    return_type = DataType.STRING,
    return_required = true)
public class ReadPage {

  @Execute
  public StringValue read(
      @Idx(index = "1", type = CREDENTIAL)
          @Pkg(label = "[[apiKey.label]]", description = "[[apiKey.description]]")
          @NotEmpty
          SecureString apiKey,
      @Idx(index = "2", type = TEXT) @Pkg(label = "[[ReadPage.url.label]]") @NotEmpty String url) {
    try {
      return new StringValue(new SpecStream(apiKey.getInsecureString()).read(url));
    } catch (IllegalArgumentException | IllegalStateException error) {
      throw new BotCommandException(error.getMessage());
    }
  }
}
